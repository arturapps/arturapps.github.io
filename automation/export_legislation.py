#!/usr/bin/env python3
import json, re, hashlib, time, os, zipfile
from pathlib import Path
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

RUN_DATE = '2026-07-29'
OUT = Path('legal_export')
DOCS_DIR = OUT / 'documents'
RAW_DIR = OUT / 'raw'
DOCS_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

DOCUMENTS = [
('labor-code','hk9900296','Трудовой кодекс Республики Беларусь'),
('decree-5','Pd1400005','Об усилении требований к руководящим кадрам и работникам организаций'),
('ukaz-45-2026','P32600045','Об обеспечении выплаты заработной платы и вознаграждений'),
('decree-29','Pd9900029','О дополнительных мерах по совершенствованию трудовых отношений, укреплению трудовой и исполнительской дисциплины'),
('law-labor-safety','H10800356','Об охране труда'),
('law-employment','H10600125','О занятости населения'),
('law-trade-unions','V19201605','О профессиональных союзах'),
('law-minimum-wage','H10200124','Об установлении и порядке повышения минимальной заработной платы'),
('law-appeals','H11100300','Об обращениях граждан и юридических лиц'),
('law-personal-data','H12100099','О защите персональных данных'),
('law-social-insurance','V19503563','Об основах государственного социального страхования'),
('law-family-benefits','H11200007','О государственных пособиях семьям, воспитывающим детей'),
('law-professional-pension','H10800322','О профессиональном пенсионном страховании'),
('law-disability-rights','H12200183','О правах инвалидов и их социальной интеграции'),
('law-external-labor-migration','H11000225','О внешней трудовой миграции'),
('resolution-569','C21300569','О мерах по реализации Закона Республики Беларусь «О государственных пособиях семьям, воспитывающим детей»'),
('resolution-average-earnings-47','W20003382','Об утверждении Инструкции о порядке исчисления среднего заработка'),
('resolution-accidents-30','C20400030','О расследовании и учете несчастных случаев на производстве и профессиональных заболеваний'),
('resolution-labor-safety-rules-53','W22137683p','Об утверждении Правил по охране труда'),
('resolution-labor-books-40','W21429094','О трудовых книжках'),
('resolution-internal-rules-46','W20003389','Об утверждении Типовых правил внутреннего трудового распорядка'),
('resolution-contract-form-1180','C29901180','Об утверждении Примерной формы контракта нанимателя с работником'),
('resolution-employment-contract-form-155','W29902550','Об установлении примерной формы трудового договора'),
('plenum-termination-9','S22300009','О применении судами законодательства при рассмотрении гражданских дел о прекращении трудовых договоров'),
('plenum-discipline-4','S21200004','О практике применения судами законодательства о трудовой дисциплине и дисциплинарной ответственности работников'),
('plenum-material-liability-2','S20200002','О применении судами законодательства о материальной ответственности работников за ущерб, причиненный нанимателю при исполнении трудовых обязанностей'),
('plenum-labor-pension-6','S22400006','О судебной практике рассмотрения дел, связанных с правом граждан на трудовую пенсию'),
]

HEADERS = {
  'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36',
  'Accept-Language': 'ru-RU,ru;q=0.9',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)
MONTHS = {'января':'01','февраля':'02','марта':'03','апреля':'04','мая':'05','июня':'06','июля':'07','августа':'08','сентября':'09','октября':'10','ноября':'11','декабря':'12'}

def norm(s):
    return re.sub(r'\s+', ' ', (s or '').replace('\xa0',' ')).strip()

def anchor(s):
    s = s.lower().replace('ё','е')
    s = re.sub(r'[^0-9a-zа-яіў]+','-',s,flags=re.I).strip('-')
    return s[:100]

def fetch(url):
    last = None
    for attempt in range(4):
        try:
            r = SESSION.get(url, timeout=60, allow_redirects=True)
            last = r
            if r.status_code == 200 and len(r.content) > 100:
                r.encoding = r.apparent_encoding or 'utf-8'
                return r
        except Exception as e:
            last = e
        time.sleep(2 + attempt * 2)
    raise RuntimeError(f'fetch failed {url}: {last}')

def detect_status(text, header):
    probe = (header + '\n' + text[:4000]).lower()
    if 'утратил силу' in probe or 'утратила силу' in probe:
        return 'repealed'
    if 'не вступил в силу' in probe:
        return 'not_in_force'
    return 'active_or_unknown'

def parse_etal(html, fallback_title, source_url):
    soup = BeautifulSoup(html, 'lxml')
    content = soup.select_one('#userContent')
    title_node = soup.select_one('#docTitlePrint .title, #docTitlePrint .titlencpi, #docTitlePrint .titleu')
    title = norm(title_node.get_text(' ', strip=True) if title_node else fallback_title)
    header_node = soup.select_one('#docTitlePrint')
    header = norm(header_node.get_text(' ', strip=True) if header_node else '')
    meta_text = norm(soup.get_text(' ', strip=True))[:20000]
    if not content:
        return {'title':title,'header':header,'contentText':'','nodes':[],'status':'no_user_content','metaText':meta_text}
    candidates = content.select('p, li, tr')
    lines = []
    seen = set()
    for node in candidates:
        classes = set(node.get('class') or [])
        if {'contenttext','changeadd'} & classes:
            continue
        text = norm(node.get_text(' ', strip=True))
        if not text or text == 'ОГЛАВЛЕНИЕ':
            continue
        if text in seen:
            continue
        seen.add(text)
        lines.append((text, classes))
    if not lines:
        text = norm(content.get_text('\n', strip=True))
        lines = [(x.strip(), set()) for x in re.split(r'\n+', text) if x.strip()]
    nodes=[]; current=''; par=0; used={}
    def unique(candidate):
        base=candidate or f'par-{len(nodes)+1}'; n=used.get(base,0)+1; used[base]=n
        return base if n==1 else f'{base}-{n}'
    for text, classes in lines:
        am=re.match(r'^Статья\s+([\dА-Яа-яІіЎў./-]+)',text,re.I)
        cm=re.match(r'^ГЛАВА\s+([\dА-Яа-яІіЎў./-]+)',text,re.I)
        sm=re.match(r'^РАЗДЕЛ\s+([\dА-Яа-яІіЎў./-]+)',text,re.I)
        pm=re.match(r'^(\d+(?:\.\d+)*)[.)]\s*',text)
        upper_title=(text.isupper() and len(text)<240)
        if am:
            current=anchor(am.group(1)); par=0; kind='article'; ident=f'art-{current}'; level=1
        elif cm:
            kind='chapter'; ident=f'chapter-{anchor(cm.group(1))}'; level=1
        elif sm:
            kind='section'; ident=f'section-{anchor(sm.group(1))}'; level=1
        elif upper_title or classes.intersection({'title','titlencpi','titleu','cap1','capu1'}):
            kind='title'; ident=f'title-{anchor(text)}'; level=1
        else:
            par+=1; kind='paragraph'; level=3
            if pm and current: ident=f'art-{current}-p-{anchor(pm.group(1))}'
            elif pm: ident=f'point-{anchor(pm.group(1))}'
            elif current: ident=f'art-{current}-par-{par}'
            else: ident=f'par-{len(nodes)+1}'
        nodes.append({'id':unique(ident),'kind':kind,'text':text,'level':level})
    content_text='\n\n'.join(n['text'] for n in nodes)
    return {'title':title,'header':header,'contentText':content_text,'nodes':nodes,'status':'parsed','metaText':meta_text}

def parse_requisites(header):
    mnum=re.search(r'№\s*([А-ЯA-Z0-9ІіЎў./-]+)',header,re.I)
    md=re.search(r'(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})',header,re.I)
    date=None
    if md: date=f'{md.group(3)}-{MONTHS[md.group(2).lower()]}-{int(md.group(1)):02d}'
    return date, mnum.group(1) if mnum else None

def edition_markers(meta):
    patterns=[r'в ред\. Закона Республики Беларусь от [^.;]{5,160}',r'в редакции [^.;]{5,160}',r'с изменениями и дополнениями[^.;]{0,200}',r'изменения и дополнения[^.;]{0,200}',r'редакц[^.;]{0,200}']
    found=[]
    for p in patterns:
        for m in re.finditer(p,meta,re.I):
            v=norm(m.group(0))
            if v not in found: found.append(v)
            if len(found)>=12: return found
    return found

report=[]
for idx,(doc_id,regnum,fallback) in enumerate(DOCUMENTS,1):
    etal=f'https://etalonline.by/document/?regnum={quote(regnum)}'
    pravo=f'https://pravo.by/document/?guid=3871&p0={quote(regnum)}'
    entry={'id':doc_id,'regnum':regnum,'fallbackTitle':fallback,'fetchedAt':RUN_DATE,'etalUrl':etal,'pravoUrl':pravo}
    try:
        r=fetch(etal)
        html=r.text
        (RAW_DIR/f'{doc_id}.html').write_text(html,encoding='utf-8')
        parsed=parse_etal(html,fallback,etal)
        date,number=parse_requisites(parsed['header'])
        text=parsed['contentText']
        status=detect_status(text,parsed['header'])
        article_count=sum(1 for n in parsed['nodes'] if n['kind']=='article')
        point_count=sum(1 for n in parsed['nodes'] if n['id'].startswith('point-') or '-p-' in n['id'])
        has_body = len(text)>=220 and len(parsed['nodes'])>=3
        likely_full = has_body and not any(x in parsed['metaText'].lower() for x in ['для просмотра полного текста необходимо','демонстрационный доступ'])
        payload={'id':doc_id,'regnum':regnum,'title':parsed['title'] or fallback,'header':parsed['header'],'docDate':date,'docNumber':number,'sourceUrl':etal,'officialUrl':pravo,'fetchedAt':RUN_DATE,'status':status,'parseStatus':parsed['status'],'contentText':text,'structure':parsed['nodes'],'contentLength':len(text),'nodeCount':len(parsed['nodes']),'articleCount':article_count,'pointCount':point_count,'likelyFull':likely_full,'checksum':hashlib.sha256(text.encode('utf-8')).hexdigest() if text else None,'editionMarkers':edition_markers(parsed['metaText'])}
        (DOCS_DIR/f'{doc_id}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
        entry.update({k:payload[k] for k in ['title','header','docDate','docNumber','status','parseStatus','contentLength','nodeCount','articleCount','pointCount','likelyFull','checksum','editionMarkers']})
        entry['result']='ok'
    except Exception as e:
        entry['result']='error'; entry['error']=repr(e)
    report.append(entry)
    print(f'[{idx}/{len(DOCUMENTS)}] {doc_id}: {entry.get("result")} {entry.get("contentLength",0)} full={entry.get("likelyFull")}',flush=True)

(OUT/'report.json').write_text(json.dumps({'generatedAt':RUN_DATE,'documents':report},ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(OUT/'legislation_export.zip','w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in OUT.rglob('*'):
        if p.is_file() and p.name!='legislation_export.zip': z.write(p,p.relative_to(OUT))
(OUT/'EXPORT_DONE.txt').write_text(f'Generated {RUN_DATE}; documents={len(report)}\n',encoding='utf-8')
