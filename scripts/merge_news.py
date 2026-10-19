"""Merge several TinyFish news runs (one per query) into ONE news_<date>.json for the backend.

Usage:
  python scripts/merge_news.py data/raw/tinyfish_news/run*.json \
      --out data/signals/groww/news_2026-10-19.json \
      --company "Billionbrains Garage Ventures (Groww)" [--collected 2026-10-19T01:40:00+05:30] [--credits 0.9]

Each input run: {"query": "...", "query_type": "company|sector_regulatory", "articles": [{title, snippet, publisher, url, date_text}]}

What it does (nothing is rewritten except dates):
  - date_text -> ISO date. "Dec 6, 2025" is exact. "Aug 26" has no year, so the year of the
    collection date is assumed (or the year before, if that would be in the future) and
    date_year_assumed=true is recorded. "2 days ago" is counted back from the collection date.
  - drops articles with no readable date, and exact duplicates (same url, or same title+publisher)
  - keeps date_text so the original is still visible
"""
import argparse, json, re, sys
from datetime import datetime, timedelta, date, timezone

IST = timezone(timedelta(hours=5, minutes=30))
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(text, today):
    """Return (iso_date or None, note or None)."""
    raw = (text or "").strip()
    if re.match(r"^[A-Za-z]{3},\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", raw):      # RSS pubDate: "Thu, 15 Oct 2026 08:30:00 GMT"
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(raw).astimezone(IST).date().isoformat(), None
        except (TypeError, ValueError):
            pass
    t = raw.lower().replace(",", "")
    if not t:
        return None, None
    if t in ("today",):
        return today.isoformat(), "relative"
    if t == "yesterday":
        return (today - timedelta(days=1)).isoformat(), "relative"
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", t)            # ISO date from the RSS converter
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat(), None
    m = re.match(r"^(\d+)\s*(minute|min|hour|hr|day|week|month)s?\s*ago$", t)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        days = {"minute": 0, "min": 0, "hour": 0, "hr": 0, "day": n, "week": 7 * n, "month": 30 * n}[unit]
        return (today - timedelta(days=days)).isoformat(), "relative" + ("-approx" if unit == "month" else "")
    m = re.match(r"^([a-z]{3})[a-z]*\.?\s+(\d{1,2})(?:\s+(\d{4}))?$", t)
    if m and m.group(1) in MONTHS:
        mon, day = MONTHS[m.group(1)], int(m.group(2))
        if m.group(3):
            return date(int(m.group(3)), mon, day).isoformat(), None
        try:
            d = date(today.year, mon, day)
        except ValueError:
            return None, None
        if d > today:
            d = date(today.year - 1, mon, day)
        return d.isoformat(), "year-assumed"
    m = re.match(r"^(\d{1,2})\s+([a-z]{3})[a-z]*\.?(?:\s+(\d{4}))?$", t)   # "26 Aug" / "26 Aug 2026"
    if m and m.group(2) in MONTHS:
        mon, day = MONTHS[m.group(2)], int(m.group(1))
        if m.group(3):
            return date(int(m.group(3)), mon, day).isoformat(), None
        d = date(today.year, mon, day)
        if d > today:
            d = date(today.year - 1, mon, day)
        return d.isoformat(), "year-assumed"
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--company", required=True)
    ap.add_argument("--collected", default=None, help="ISO datetime the runs were done (default: now, IST)")
    ap.add_argument("--credits", type=float, default=None)
    a = ap.parse_args()

    collected = datetime.fromisoformat(a.collected) if a.collected else datetime.now(IST)
    today = collected.date()
    out, seen_url, seen_title = [], set(), set()
    stats = {"read": 0, "no_date": 0, "dupes": 0}
    for path in a.runs:
        run = json.load(open(path, encoding="utf-8"))
        qt = run.get("query_type")
        if qt not in ("company", "sector_regulatory"):
            print(f"WARNING {path}: query_type is '{qt}' (expected company or sector_regulatory)", file=sys.stderr)
        for x in run.get("articles", []):
            stats["read"] += 1
            iso, note = parse_date(x.get("date_text") or x.get("date"), today)
            if not iso:
                stats["no_date"] += 1
                print(f"  dropped (no readable date '{x.get('date_text')}'): {x.get('title')}", file=sys.stderr)
                continue
            if re.search(r"\s", x.get("url") or ""):
                stats["no_date"] += 1
                print(f"  dropped (broken link, contains a space): {x.get('title')}", file=sys.stderr)
                continue
            key_t = (re.sub(r"\W+", "", (x.get("title") or "").lower()), (x.get("publisher") or "").lower())
            if not x.get("url") or x["url"] in seen_url or key_t in seen_title:
                stats["dupes"] += 1
                continue
            seen_url.add(x["url"]); seen_title.add(key_t)
            rec = {"title": x.get("title"), "snippet": x.get("snippet") or "", "publisher": x.get("publisher"),
                   "url": x["url"], "date": iso, "date_text": x.get("date_text"),
                   "query": run.get("query"), "query_type": qt}
            if note == "year-assumed":
                rec["date_year_assumed"] = True
            out.append(rec)
    out.sort(key=lambda r: r["date"], reverse=True)
    doc = {"company": a.company, "signal": "news", "collected_at": collected.isoformat(timespec="seconds"),
           "collected_by": "tinyfish", "source": "Google News search results (link redirects via news.google.com)",
           "articles": out}
    if a.credits is not None:
        doc["credits_used"] = a.credits
    json.dump(doc, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"read {stats['read']}  kept {len(out)}  no-date {stats['no_date']}  duplicates {stats['dupes']}  -> {a.out}")
    for r in out:
        print(f"  {r['date']}{'*' if r.get('date_year_assumed') else ' '} [{r['query_type']}] {r['publisher']}: {r['title'][:70]}")
    print("  (* = year was not shown, assumed)")


if __name__ == "__main__":
    main()
