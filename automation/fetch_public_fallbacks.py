#!/usr/bin/env python3
import json,re,time,zipfile,hashlib
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

OUT=Path('fallback_export'); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36','Accept-Language':'ru-RU,ru;q=0.9','Accept':'text/html,application/xhtml+xml'})

def norm(s): return re.sub(r'\s+',' ',(s or '').replace('\xa0',' ')).strip()
def get(url):
 for i in range(4):
  try:
   r=S.get(url,timeout=60,allow_redirects=True); r.encoding=r.apparent_encoding or 'utf-8'
   if r.status_code==200 and len(r.text)>300: return r
  except Exception: pass
  time.sleep(2+i)
 raise RuntimeError('fetch failed '+url)

def make(doc_id,title,requisites,edition,official,source,norms,notes=''):
 text='\n\n'.join(n['text'] for n in norms)
 return {'id':doc_id,'title':title,'requisites':requisites,'editionLabel':edition,'officialUrl':official,'sourceUrl':source,'fetchedAt':'2026-07-29','norms':norms,'contentLength':len(text),'normCount':len(norms),'checksum':hashlib.sha256(text.encode()).hexdigest(),'notes':notes}

def scrape_zakony(base,doc_id,title,requisites,edition,official,max_article=80):
 norms=[]; missing=[]
 for n in range(1,max_article+1):
  url=f'{base}/{n}.htm'
  try: r=get(url)
  except Exception:
   if n<=3: missing.append(n)
   elif n>len(norms)+4: break
   continue
  soup=BeautifulSoup(r.text,'lxml')
  h=None
  for tag in soup.find_all(['h1','h2','h3']):
   if re.search(rf'Статья\s+{n}(?:\D|$)',norm(tag.get_text(' ',strip=True)),re.I): h=tag; break
  if not h:
   body=norm(soup.get_text('\n',strip=True)); m=re.search(rf'(Статья\s+{n}\.?[^\n]{{0,250}})\n(.+?)(?=Ваш гид|Комментарии|Статья\s+{n+1}\b|$)',body,re.S|re.I)
   if not m:
    if n<=3: missing.append(n)
    elif n>len(norms)+4: break
    continue
   heading=norm(m.group(1)); text=norm(m.group(2))
  else:
   heading=norm(h.get_text(' ',strip=True)); parts=[]
   for x in h.find_all_next():
    if x is not h and x.name in ['h1','h2','h3'] and re.search(r'Статья\s+\d+',norm(x.get_text(' ',strip=True)),re.I): break
    if x.name in ['script','style','nav','form','footer','header']: continue
    if x.name in ['p','div','li']:
     t=norm(x.get_text(' ',strip=True))
     if not t or t==heading or 'Ваш гид в законодательстве' in t or 'Комментарий'==t: continue
     if any(bad in t for bad in ['Добавить комментарий','Навигация по документу','© 2026']): continue
     if t not in parts: parts.append(t)
    if sum(map(len,parts))>30000: break
   text='\n\n'.join(parts)
  text=re.sub(r'\s*Ст\.\s*\d+.*?Комментарий.*$','',text,flags=re.S|re.I).strip()
  if len(text)<20: continue
  norms.append({'id':f'article-{n}','label':f'Статья {n}','title':re.sub(r'^Статья\s+\d+\.?\s*','',heading,flags=re.I).strip(' .-') or f'Статья {n}','text':text,'keywords':[title.lower(),f'статья {n}']})
 if missing or len(norms)<3: raise RuntimeError(f'incomplete {doc_id}: norms={len(norms)} missing={missing}')
 return make(doc_id,title,requisites,edition,official,base,norms,'Публичная постатейная копия; реквизиты и редакция сверены отдельно по официальной карточке.')

def scrape_prg(url,doc_id,title,requisites,edition,official):
 r=get(url); soup=BeautifulSoup(r.text,'lxml')
 for x in soup(['script','style','nav','header','footer','form']): x.decompose()
 lines=[]
 for el in soup.find_all(['h1','h2','h3','p','li','div']):
  t=norm(el.get_text(' ',strip=True))
  if not t or len(t)>5000: continue
  if any(b in t for b in ['Если у вас нет логина','Зарегистрируйтесь','Посмотреть закладки','Добавить комментарий','Поставить закладку']): continue
  if t not in lines: lines.append(t)
 start=0
 for i,t in enumerate(lines):
  if title.lower() in t.lower() or 'В целях обеспечения своевременной выплаты' in t: start=i; break
 body=lines[start:]
 # retain legal-looking paragraphs; stop at service footer
 out=[]
 for t in body:
  if any(b in t for b in ['Информация о документе','Документ входит в комплект','Скачать в Word']):
   if out: break
  if t not in out: out.append(t)
 text='\n\n'.join(out)
 # split at top-level points, preserving subpoints within point 1
 matches=list(re.finditer(r'(?m)(?=^\d+\.\s)',text))
 norms=[]
 if matches:
  prefix=text[:matches[0].start()].strip()
  if prefix: norms.append({'id':'preamble','label':'Преамбула','title':'Цель Указа','text':prefix,'keywords':['заработная плата','вознаграждение']})
  for i,m in enumerate(matches):
   chunk=text[m.start():(matches[i+1].start() if i+1<len(matches) else len(text))].strip()
   num=re.match(r'(\d+)\.',chunk).group(1)
   norms.append({'id':f'point-{num}','label':f'Пункт {num}','title':f'Пункт {num}','text':chunk,'keywords':['заработная плата','вознаграждение','инспекция труда']})
 else:
  norms=[{'id':'text','label':'Текст','title':title,'text':text,'keywords':['заработная плата','вознаграждение']}]
 if len(text)<2000 or 'Полный текст доступен' in text: raise RuntimeError(f'incomplete {doc_id}: {len(text)}')
 return make(doc_id,title,requisites,edition,official,url,norms,'Текст получен из публичной копии; реквизиты и вступление в силу сверены по официальной карточке.')

def scrape_generic(url,doc_id,title,requisites,edition,official,minlen=10000):
 r=get(url); soup=BeautifulSoup(r.text,'lxml')
 for x in soup(['script','style','nav','header','footer','form']): x.decompose()
 text='\n'.join(norm(x.get_text(' ',strip=True)) for x in soup.find_all(['h1','h2','h3','p','li']) if norm(x.get_text(' ',strip=True)))
 if any(x in text for x in ['Полный текст доступен после регистрации','Текст документа доступен только пользователям']) or len(text)<minlen: raise RuntimeError(f'incomplete {doc_id}: {len(text)}')
 norms=[]; chunks=re.split(r'(?m)(?=^\d+(?:\.\d+)*[.)]\s)',text)
 for i,c in enumerate(chunks):
  c=c.strip()
  if len(c)<10: continue
  m=re.match(r'^(\d+(?:\.\d+)*)[.)]',c); lab=f'Пункт {m.group(1)}' if m else ('Преамбула' if not norms else f'Раздел {i+1}')
  norms.append({'id':f'norm-{i+1}','label':lab,'title':lab,'text':c,'keywords':[title.lower()]})
 return make(doc_id,title,requisites,edition,official,url,norms,'Публичная копия; полнота проверена автоматическим порогом.')

results=[]; errors=[]
tasks=[
 ('minimum',lambda:scrape_zakony('https://zakony-by.com/zakon_rb_ob_ustanovlenii_i_poryadke_povysheniya_razmera_minimalnoj_zarplaty','law-minimum-wage','Об установлении и порядке повышения минимальной заработной платы','17 июля 2002 г. № 124-З','Редакция с изменениями Закона от 8 июля 2024 г. № 25-З; действует с 1 января 2025 г.','https://pravo.by/document/?guid=3871&p0=H10200124',15)),
 ('migration',lambda:scrape_zakony('https://zakony-by.com/zakon_rb_o_vneshnej_trudovoj_migratsii','law-external-labor-migration','О внешней трудовой миграции','30 декабря 2010 г. № 225-З','Редакция с изменениями Закона от 16 марта 2026 г. № 134-З; действует с 21 марта 2026 г.','https://pravo.by/document/?guid=3871&p0=H11000225',50)),
 ('ukaz45',lambda:scrape_prg('https://prg.kz/m/amp/document/33949727/','ukaz-45-2026','Об обеспечении выплаты заработной платы и вознаграждений','12 февраля 2026 г. № 45','Действующая редакция; основные положения действуют с 15 мая 2026 г.','https://pravo.by/document/?guid=3871&p0=P32600045')),
 ('average47',lambda:scrape_generic('https://prg.kz/m/amp/document/31039391/','resolution-average-earnings-47','Об утверждении Инструкции о порядке исчисления среднего заработка','10 апреля 2000 г. № 47','Редакция с изменениями по состоянию на 31 октября 2022 г.; действует с 1 января 2023 г.','https://pravo.by/document/?guid=3871&p0=W20003382',12000)),
 ('books40',lambda:scrape_generic('https://base.spinform.ru/show_doc.fwx?rgn=69669','resolution-labor-books-40','О трудовых книжках','16 июня 2014 г. № 40','Редакция с изменениями постановления от 8 мая 2026 г. № 41','https://pravo.by/document/?guid=3871&p0=W21429094',20000)),
]
for name,fn in tasks:
 try:
  d=fn(); results.append(d); (OUT/(d['id']+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8'); print(name,'OK',d['contentLength'],d['normCount'])
 except Exception as e:
  errors.append({'task':name,'error':repr(e)}); print(name,'ERROR',repr(e))
(OUT/'report.json').write_text(json.dumps({'generatedAt':'2026-07-29','documents':[{k:v for k,v in d.items() if k!='norms'} for d in results],'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(OUT/'fallback_acts.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in OUT.glob('*.json'): z.write(p,p.name)
