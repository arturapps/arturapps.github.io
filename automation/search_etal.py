import requests, json, re
from bs4 import BeautifulSoup
from urllib.parse import quote, urljoin
queries = [
'Об утверждении Правил по охране труда 1 июля 2021 53',
'Об установлении примерной формы трудового договора 27 декабря 1999 155',
'О трудовых книжках 16 июня 2014 40',
'Инструкция о порядке исчисления среднего заработка 10 апреля 2000 47',
'Об установлении и порядке повышения минимальной заработной платы 124-З',
'О внешней трудовой миграции 225-З',
'Об обеспечении выплаты заработной платы и вознаграждений 45 2026',
]
s=requests.Session(); s.headers.update({'User-Agent':'Mozilla/5.0','Accept-Language':'ru-RU,ru;q=0.9'})
out=[]
for q in queries:
    urls=[f'https://etalonline.by/search/?search_str={quote(q)}', f'https://etalonline.by/search/?search_str={quote(q)}&adv_s=0']
    found=[]
    for u in urls:
        try:
            r=s.get(u,timeout=60); r.encoding=r.apparent_encoding or 'utf-8'
            soup=BeautifulSoup(r.text,'lxml')
            for a in soup.select('a[href*="/document/"][href*="regnum="]'):
                href=urljoin(u,a.get('href'))
                text=' '.join(a.get_text(' ',strip=True).split())
                m=re.search(r'[?&]regnum=([^&#]+)',href,re.I)
                item={'text':text,'href':href,'regnum':m.group(1) if m else None}
                if item not in found: found.append(item)
            for a in soup.select('a[href*="p0="]'):
                href=urljoin(u,a.get('href'))
                text=' '.join(a.get_text(' ',strip=True).split())
                m=re.search(r'[?&]p0=([^&#]+)',href,re.I)
                item={'text':text,'href':href,'regnum':m.group(1) if m else None}
                if item not in found: found.append(item)
        except Exception as e:
            found.append({'error':repr(e),'url':u})
    out.append({'query':q,'results':found[:100]})
open('legal_export/search_results.json','w',encoding='utf-8').write(json.dumps(out,ensure_ascii=False,indent=2))
