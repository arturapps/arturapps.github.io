import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

DOCS = [
    ("labor-code", "hk9900296"),
    ("decree-5", "Pd1400005"),
    ("ukaz-45-2026", "P32600045"),
    ("decree-29", "Pd9900029"),
    ("law-labor-safety", "H10800356"),
    ("law-employment", "H10600125"),
    ("law-trade-unions", "V19201605"),
    ("law-minimum-wage", "H10200124"),
    ("law-appeals", "H11100300"),
    ("law-personal-data", "H12100099"),
    ("law-social-insurance", "V19503563"),
    ("law-family-benefits", "H11200007"),
    ("law-professional-pension", "H10800322"),
    ("law-disability-rights", "H12200183"),
    ("law-external-labor-migration", "H11000225"),
    ("resolution-569", "C21300569"),
    ("resolution-average-earnings-47", "W20003382"),
    ("resolution-accidents-30", "C20400030"),
    ("resolution-labor-safety-rules-53", "W22137683p"),
    ("resolution-labor-books-40", "W21429094"),
    ("resolution-internal-rules-46", "W20003389"),
    ("resolution-contract-form-1180", "C29901180"),
    ("resolution-employment-contract-form-155", "W29902550"),
    ("plenum-termination-9", "S22300009"),
    ("plenum-discipline-4", "S21200004"),
    ("plenum-material-liability-2", "S20200002"),
    ("plenum-labor-pension-6", "S22400006"),
]

OUT = Path("legal_export")
OUT.mkdir(exist_ok=True)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
})


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def parse_doc(doc_id: str, regnum: str):
    url = f"https://etalonline.by/document/?regnum={quote(regnum)}"
    r = session.get(url, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    root = soup.select_one("#userContent")
    title_root = soup.select_one("#docTitlePrint")
    header = norm(title_root.get_text(" ", strip=True) if title_root else "")
    title_el = soup.select_one("#docTitlePrint .title, #docTitlePrint .titlencpi")
    title = norm(title_el.get_text(" ", strip=True) if title_el else header)
    if not root:
        raise RuntimeError("missing #userContent")

    nodes = []
    for p in root.select("p"):
        classes = set(p.get("class") or [])
        if "contenttext" in classes or "changeadd" in classes:
            continue
        text = norm(p.get_text(" ", strip=True))
        if not text or text == "ОГЛАВЛЕНИЕ":
            continue
        kind = "paragraph"
        if re.match(r"^Статья\s+", text, re.I):
            kind = "article"
        elif re.match(r"^ГЛАВА\s+", text, re.I):
            kind = "chapter"
        elif re.match(r"^РАЗДЕЛ\s+", text, re.I):
            kind = "section"
        elif re.match(r"^\d+(?:\.\d+)*[.)]\s*", text):
            kind = "point"
        elif classes.intersection({"title", "titlencpi", "titleu", "cap1", "capu1"}):
            kind = "title"
        nodes.append({"kind": kind, "text": text})

    content = "\n\n".join(n["text"] for n in nodes)
    article_count = sum(1 for n in nodes if n["kind"] == "article")
    point_count = sum(1 for n in nodes if n["kind"] == "point")
    suspicious = any(x in content.lower() for x in [
        "для просмотра документа необходимо", "приобретите доступ", "войдите в систему",
        "демонстрационный доступ", "фрагмент документа"
    ])
    complete = len(content) >= 1000 and len(nodes) >= 10 and not suspicious

    data = {
        "id": doc_id,
        "regnum": regnum,
        "sourceUrl": url,
        "title": title,
        "header": header,
        "fetchedAt": "2026-07-29",
        "contentLength": len(content),
        "nodeCount": len(nodes),
        "articleCount": article_count,
        "pointCount": point_count,
        "complete": complete,
        "nodes": nodes if complete else [],
        "contentText": content if complete else "",
    }
    (OUT / f"{doc_id}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {k: data[k] for k in ["id", "regnum", "sourceUrl", "title", "header", "fetchedAt", "contentLength", "nodeCount", "articleCount", "pointCount", "complete"]}


results = []
for i, (doc_id, regnum) in enumerate(DOCS, 1):
    try:
        item = parse_doc(doc_id, regnum)
        item["status"] = "ok"
    except Exception as exc:
        item = {"id": doc_id, "regnum": regnum, "complete": False, "status": "error", "error": str(exc)}
    results.append(item)
    print(f"[{i}/{len(DOCS)}] {doc_id}: {item['status']} complete={item.get('complete')}")
    time.sleep(0.35)

(OUT / "index.json").write_text(json.dumps({"generated": "2026-07-29", "documents": results}, ensure_ascii=False, indent=2), encoding="utf-8")
