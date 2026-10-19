"""Reads Person A's files whatever their exact shape is, and turns them into one internal shape.
Every function returns (doc, warnings). Nothing is invented: if a field is missing we say so."""
import re
from pathlib import Path
from .dates import parse_any
from datetime import date

REVIEW_LIST_KEYS = ["reviews", "data", "items", "results", "records"]
JOB_LIST_KEYS = ["jobs", "listings", "roles", "openings", "positions", "sample_roles", "job_listings"]
POST_LIST_KEYS = ["posts", "results", "items", "data", "threads", "records"]


def _first(d, keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default


def _list_in(raw, keys):
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for k in keys:
            if isinstance(raw.get(k), list):
                return raw[k]
    return []


def _ref_date(raw):
    ca = raw.get("collected_at") if isinstance(raw, dict) else None
    d = parse_any(ca) if ca else None
    return date.fromisoformat(d) if d else None


def _label_from_filename(path, slug, kind):
    stem = Path(path).stem.lower()
    stem = re.sub(rf"^{re.escape(slug)}_?", "", stem)
    stem = re.sub(rf"_?{kind}.*$", "", stem)
    stem = stem.replace("_", " ").strip()
    return stem.title() if stem else slug.title()


def normalize_reviews(raw, path, slug):
    w = []
    items = _list_in(raw, REVIEW_LIST_KEYS)
    meta = raw if isinstance(raw, dict) else {}
    ref = _ref_date(meta)
    out, bad_rating, bad_date, no_text = [], 0, 0, 0
    for r in items:
        if not isinstance(r, dict):
            continue
        try:
            rating = int(round(float(_first(r, ["rating", "score", "stars", "star", "rate"]))))
            if not 1 <= rating <= 5:
                raise ValueError
        except (TypeError, ValueError):
            bad_rating += 1
            continue
        d = parse_any(_first(r, ["date", "at", "time", "reviewDate", "review_date", "published", "created_at", "dateTime", "timestamp"]), ref)
        if not d:
            bad_date += 1
            continue
        text = str(_first(r, ["text", "content", "review", "body", "comment", "reviewText", "review_text", "message"], "") or "")
        if not text.strip():
            no_text += 1
        out.append({"date": d, "rating": rating, "text": text})
    if not items:
        w.append("no review list found (looked for: " + ", ".join(REVIEW_LIST_KEYS) + ")")
    if bad_rating:
        w.append(f"{bad_rating} review(s) skipped: rating missing or not 1-5")
    if bad_date:
        w.append(f"{bad_date} review(s) skipped: date missing or unreadable")
    if no_text:
        w.append(f"{no_text} review(s) have no text (counted in ratings only)")
    url = _first(meta, ["url", "app_url", "source_url", "play_store_url", "link", "store_url"])
    if not url:
        w.append("no url in the file: evidence from it cannot link to a source")
    if not meta.get("collected_at"):
        w.append("no collected_at in the file: cannot show when this was collected")
    doc = {"app_name": _first(meta, ["app_name", "app", "name", "title"]) or (_label_from_filename(path, slug, "playstore") + " Play Store"),
           "url": url, "overall_rating": _first(meta, ["overall_rating", "rating", "score", "avg_rating", "average_rating"]) if not isinstance(raw, list) else None,
           "total_reviews": _first(meta, ["total_reviews", "ratings_count", "reviews_count", "total_ratings"]),
           "collected_at": meta.get("collected_at"), "collected_by": meta.get("collected_by"), "reviews": out}
    return doc, w


def normalize_jobs(raw, path, slug):
    w = []
    meta = raw if isinstance(raw, dict) else {}
    lst = _list_in(raw, JOB_LIST_KEYS)
    n = _first(meta, ["open_roles", "job_count", "total_jobs", "jobs_count", "count", "total", "openings_count", "num_jobs"])
    try:
        n = int(n) if n is not None else None
    except (TypeError, ValueError):
        n = None
    if n is None and lst:
        n = len(lst)
        w.append(f"no job count in the file; using the number of listed roles ({n}), which may be only a sample")
    if n is None:
        w.append("could not find a job count (looked for open_roles, job_count, total_jobs, or a list of jobs)")
    titles = []
    for r in lst[:50]:
        t = r if isinstance(r, str) else _first(r, ["title", "role", "name", "position", "job_title"])
        if t:
            titles.append({"title": str(t)})
    url = _first(meta, ["url", "careers_url", "source_url", "link", "careers_page"])
    if not url:
        w.append("no url in the file: evidence from it cannot link to a source")
    if not meta.get("collected_at"):
        w.append("no collected_at in the file: cannot show when this was collected")
    prev = _first(meta, ["previous_open_roles", "previous_count"])
    doc = {"open_roles": n, "sample_roles": titles, "url": url, "collected_at": meta.get("collected_at"),
           "collected_by": meta.get("collected_by"), "previous_open_roles": prev}
    return doc, w


def normalize_reddit(raw, path, slug):
    w = []
    meta = raw if isinstance(raw, dict) else {}
    ref = _ref_date(meta)
    out, no_url, no_date = [], 0, 0
    for p in _list_in(raw, POST_LIST_KEYS):
        if not isinstance(p, dict):
            continue
        url = _first(p, ["url", "link", "permalink", "post_url"])
        if url and str(url).startswith("/"):
            url = "https://www.reddit.com" + url
        if not url:
            no_url += 1
            continue
        d = parse_any(_first(p, ["date", "created_utc", "created", "created_at", "posted", "time", "timestamp"]), ref)
        if not d:
            no_date += 1
        out.append({"title": str(_first(p, ["title", "headline"], "")),
                    "snippet": str(_first(p, ["snippet", "selftext", "body", "text", "content", "description"], "") or ""),
                    "subreddit": str(_first(p, ["subreddit", "community", "sub"], "?")).replace("r/", ""),
                    "url": url, "date": d or ""})
    if no_url:
        w.append(f"{no_url} post(s) skipped: no link")
    if no_date:
        w.append(f"{no_date} post(s) have no readable date (kept, but undated)")
    if not out:
        w.append("no usable posts found")
    if not meta.get("collected_at"):
        w.append("no collected_at in the file: cannot show when this was collected")
    return {"posts": out, "collected_at": meta.get("collected_at"), "collected_by": meta.get("collected_by")}, w
