"""Turn a saved Google News RSS page (XML) into a 'run' file the merge script understands.

Usage:
  python scripts/rss_to_run.py rss5.xml data/raw/tinyfish_news/run5.json \
      --query "SEBI closing auction session derivatives" --query-type sector_regulatory [--max 10]

The XML is whatever TinyFish fetched, saved unedited. Dates come from each item's pubDate (converted to IST).
"""
import argparse, json, re
import xml.etree.ElementTree as ET
from datetime import timezone, timedelta
from email.utils import parsedate_to_datetime

IST = timezone(timedelta(hours=5, minutes=30))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xml"); ap.add_argument("out")
    ap.add_argument("--query", required=True)
    ap.add_argument("--query-type", required=True, choices=["company", "sector_regulatory"])
    ap.add_argument("--max", type=int, default=10)
    a = ap.parse_args()
    text = open(a.xml, encoding="utf-8").read()
    text = text[text.index("<"):]                      # tolerate junk before the XML
    root = ET.fromstring(text)
    arts = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        pub = (it.findtext("source") or "").strip()
        if pub and title.endswith(" - " + pub):          # Google appends ' - Publisher' to titles
            title = title[: -len(pub) - 3]
        try:
            d = parsedate_to_datetime(it.findtext("pubDate")).astimezone(IST).date().isoformat()
        except (TypeError, ValueError):
            continue
        desc = re.sub(r"<[^>]+>", " ", it.findtext("description") or "")
        desc = re.sub(r"\s+", " ", desc).strip()
        arts.append({"title": title, "publisher": pub, "url": (it.findtext("link") or "").strip(),
                     "date_text": d, "snippet": "" if desc.startswith(title) else desc})
    arts = arts[: a.max]
    json.dump({"query": a.query, "query_type": a.query_type, "articles": arts}, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{len(arts)} articles -> {a.out}")


if __name__ == "__main__":
    main()
