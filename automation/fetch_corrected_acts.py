#!/usr/bin/env python3
import json,re,zipfile,hashlib
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
OUT=Path('corrected_export'); OUT.mkdir(exist_ok=True)
DOCS=[('resolution-labor-safety-rules-53','w22137152p','Об утверждении Правил по охране труда'),('resolution-employment-contract-form-155','w20002550','Об установлении примерной формы трудового договора')]
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0','Accept-Language':'ru-RU,ru;q=0.9'})
def norm(v): return re.sub(r'\s+',' ',(v or '').replace('\xa0',' ')).strip()
def slug(v): return re.sub(r'[^0-9a-zа-яіў]+','-',v.lower().replace('ё','е')).strip('-')[:100]
def parse(doc_id,regnum,fallback):
 u=f'https://etalonline.by/document/?regnum={quote(regnum)}'; r=s.get(u,timeout=90); r.raise_for_status(); r.encoding=r.apparent_encoding or 'utf-8'; soup=BeautifulSoup(r.text,'lxml')
 root=soup.select_one('#userContent'); head=norm((soup.select_one('#docTitlePrint') or soup).get_text(' ',strip=True)); title=norm((soup.select_one('#docTitlePrint .title, #docTitlePrint .titlencpi, #docTitlePrint .titleu') or soup.new_tag('span')).get_text(' ',strip=True)) or fallback
 if not root: raise RuntimeError('no #userContent')
 lines=[]; seen=set()
 for n in root.select('p,li,tr'):
  c=set(n.get('class') or [])
  if {'contenttext','changeadd'} & c: continue
  t=norm(n.get_text(' ',strip=True))
  if not t or t=='ОГЛАВЛЕНИЕ' or t in seen: continue
  seen.add(t); lines.append((t,c))
 nodes=[]; cur=''; par=0; used={}
 def unique(x):
  used[x]=used.get(x,0)+1; return x if used[x]==1 else f'{x}-{used[x]}'
 for t,c in lines:
  a=re.match(r'^Статья\s+([\dА-Яа-яІіЎў./-]+)',t,re.I); ch=re.match(r'^ГЛАВА\s+([\dА-Яа-яІіЎў./-]+)',t,re.I); sec=re.match(r'^РАЗДЕЛ\s+([\dА-Яа-яІіЎў./-]+)',t,re.I); p=re.match(r'^(\d+(?:\.\d+)*)[.)]\s*',t)
  if a: cur=slug(a.group(1)); par=0; kind='article'; ident='art-'+cur; level=1
  elif ch: kind='chapter'; ident='chapter-'+slug(ch.group(1)); level=1
  elif sec: kind='section'; ident='section-'+slug(sec.group(1)); level=1
  elif t.isupper() and len(t)<240: kind='title'; ident='title-'+slug(t); level=1
  else:
   par+=1; kind='paragraph'; level=3
   ident=('art-'+cur+'-p-'+slug(p.group(1))) if p and cur else ('point-'+slug(p.group(1))) if p else ('art-'+cur+'-par-'+str(par)) if cur else 'par-'+str(len(nodes)+1)
  nodes.append({'id':unique(ident),'kind':kind,'text':t,'level':level})
 text='\n\n'.join(x['text'] for x in nodes); lower=norm(soup.get_text(' ',strip=True)).lower(); full=len(text)>1000 and 'текст документа доступен только пользователям' not in lower and 'документ показан в сокращенном' not in lower
 return {'id':doc_id,'regnum':regnum,'title':title,'header':head,'sourceUrl':u,'officialUrl':f'https://pravo.by/document/?guid=3871&p0={regnum}','fetchedAt':'2026-07-29','contentText':text,'structure':nodes,'contentLength':len(text),'nodeCount':len(nodes),'articleCount':sum(x['kind']=='article' for x in nodes),'likelyFull':full,'checksum':hashlib.sha256(text.encode()).hexdigest()}
res=[]
for x in DOCS:
 d=parse(*x); res.append(d); (OUT/(x[0]+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'report.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(OUT/'corrected_acts.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in OUT.glob('*.json'): z.write(p,p.name)
