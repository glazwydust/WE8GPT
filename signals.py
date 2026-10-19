"""All the counting happens here, in plain Python. No LLM, no guessing.

Input  : dict(reviews=[doc,...], jobs=[doc,...], reddit=[doc,...], news_classified=doc|None)
Output : (items, summary, risk)
  items   - numbered evidence the LLM may cite (item_id -> url, date, text)
  summary - numbers + simple rule flags, shown on the dashboard too
  risk    - speculation / opinion news, kept OUT of verdicts
"""
import re
from datetime import date
from . import config

SERVICE_WORDS = [
    "withdraw", "payment", "payout", "refund", "upi", "crash", "hang", "freez", "glitch",
    "not working", "doesn't work", "does not work", "login", "log in", "otp", "kyc",
    "support", "customer care", "no response", "order fail", "order not", "stuck",
    "slow", "server", "down", "error", "bug", "charges", "hidden", "brokerage",
    "margin call", "square off", "squared off", "blocked", "suspended",
    # food / grocery delivery service complaints (Eternal: Zomato, Blinkit)
    "late delivery", "delayed", "not delivered", "missing item", "wrong order", "cancelled", "cancel",
    "rider", "delivery partner", "refund not", "spoiled", "stale", "expired",
]


def _d(s):
    return date.fromisoformat(str(s)[:10])


def _cap(s, n=config.TEXT_CAP):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def is_service_complaint(text, rating):
    t = (text or "").lower()
    return rating is not None and rating <= 2 and any(w in t for w in SERVICE_WORDS)


def _group(rs):
    n = len(rs)
    if n == 0:
        return {"n": 0}
    return {"n": n,
            "avg": round(sum(r["rating"] for r in rs) / n, 2),
            "one_star_pct": round(100 * sum(1 for r in rs if r["rating"] == 1) / n, 1),
            "service_pct": round(100 * sum(1 for r in rs if is_service_complaint(r["text"], r["rating"])) / n, 1)}


def review_stats(doc):
    rs = []
    for r in doc.get("reviews", []):
        try:
            rs.append({"date": _d(r["date"]), "rating": int(r["rating"]), "text": r.get("text", "")})
        except (KeyError, ValueError, TypeError):
            continue
    if not rs:
        return None
    ref = max(r["date"] for r in rs)
    w = config.REVIEW_WINDOW_DAYS
    recent = [r for r in rs if (ref - r["date"]).days < w]
    prior = [r for r in rs if w <= (ref - r["date"]).days < 2 * w]
    return {"ref_date": ref, "recent": recent, "prior": prior,
            "g_recent": _group(recent), "g_prior": _group(prior), "total": len(rs),
            "first_date": min(r["date"] for r in rs)}


def build(data):
    items, summary, flags = [], {}, []

    # ---------- reviews (one block per app) ----------
    docs = [d for d in (data.get("reviews") or []) if d]
    summary["reviews"] = []
    sample_n = 0
    per_app = max(5, config.MAX_REVIEW_SAMPLES // max(1, len(docs)))
    for k, rv in enumerate(docs, 1):
        st = review_stats(rv)
        app = rv.get("app_name") or f"App {k}"
        url = rv.get("url")
        if not st:
            summary["reviews"].append({"app": app, "usable_reviews": 0})
            continue
        gr, gp = st["g_recent"], st["g_prior"]
        ok = gr["n"] >= config.MIN_REVIEWS_PER_WINDOW and gp["n"] >= config.MIN_REVIEWS_PER_WINDOW
        txt = (f"{app}: reviews in the last {config.REVIEW_WINDOW_DAYS} days up to {st['ref_date']}: "
               f"{gr['n']} reviews, average {gr.get('avg')}, {gr.get('one_star_pct')}% one-star, "
               f"{gr.get('service_pct')}% service complaints. ")
        if gp["n"]:
            txt += (f"Previous {config.REVIEW_WINDOW_DAYS} days: {gp['n']} reviews, average {gp.get('avg')}, "
                    f"{gp.get('one_star_pct')}% one-star, {gp.get('service_pct')}% service complaints. ")
        if rv.get("overall_rating") not in (None, ""):
            txt += f"Overall store rating {rv['overall_rating']}. "
        txt += f"Dataset: {st['total']} reviews from {st['first_date']} to {st['ref_date']}."
        if not ok:
            txt += " Too few reviews in one of the windows to call a trend."
        items.append({"item_id": f"m{k}", "signal": "reviews", "title": f"{app} review statistics",
                      "source_url": url, "date": str(st["ref_date"]), "text": txt})
        summary["reviews"].append({"app": app, "recent": gr, "prior": gp, "comparable": ok, "ref_date": str(st["ref_date"]),
                                   "overall_rating": rv.get("overall_rating"), "total_reviews_in_file": st["total"]})
        if ok:
            if gr["one_star_pct"] - gp["one_star_pct"] >= config.ONE_STAR_RISE_PP:
                flags.append(f"{app}: one-star share rose from {gp['one_star_pct']}% to {gr['one_star_pct']}%.")
            if gp["avg"] - gr["avg"] >= config.AVG_RATING_DROP:
                flags.append(f"{app}: average rating fell from {gp['avg']} to {gr['avg']}.")
            if gr["service_pct"] - gp["service_pct"] >= config.SERVICE_COMPLAINT_RISE_PP:
                flags.append(f"{app}: service complaints rose from {gp['service_pct']}% to {gr['service_pct']}%.")
        rec = sorted(st["recent"], key=lambda r: r["date"], reverse=True)
        svc = [r for r in rec if is_service_complaint(r["text"], r["rating"])]
        oth = [r for r in rec if r not in svc]
        pick = svc[: (per_app * 3) // 5] + oth
        pick = pick[:per_app]
        for r in pick:
            sample_n += 1
            items.append({"item_id": f"r{sample_n}", "signal": "reviews", "title": f"{app} review ({r['rating']} star)",
                          "source_url": url, "date": str(r["date"]), "text": _cap(r["text"])})

    # ---------- jobs ----------
    summary["jobs"] = []
    for k, jb in enumerate([d for d in (data.get("jobs") or []) if d], 1):
        n = jb.get("open_roles")
        if n is None:
            continue
        prev_n = jb.get("previous_open_roles")
        if k == 1 and data.get("jobs_prev") and data["jobs_prev"].get("open_roles"):
            prev_n = data["jobs_prev"]["open_roles"]
        txt = f"Careers page showed {n} open roles" + (f" on {str(jb['collected_at'])[:10]}." if jb.get("collected_at") else " (collection date not recorded).")
        info = {"open_roles": n, "collected_at": jb.get("collected_at"), "url": jb.get("url")}
        if prev_n:
            ch = round(100 * (n - prev_n) / prev_n, 1)
            txt += f" Earlier snapshot: {prev_n} roles ({ch:+}%)."
            info.update(previous=prev_n, change_pct=ch)
            if ch <= -config.JOBS_DROP_PCT:
                flags.append(f"Open roles fell {abs(ch)}% between snapshots.")
        else:
            txt += " Only one snapshot, so no trend can be shown."
        titles = [r.get("title") for r in jb.get("sample_roles", [])][:10]
        if titles:
            txt += " Sample roles: " + "; ".join(_cap(t, 60) for t in titles if t) + "."
        items.append({"item_id": f"j{k}", "signal": "jobs", "title": "Careers page job count", "source_url": jb.get("url"),
                      "date": str(jb.get("collected_at") or "")[:10], "text": txt})
        summary["jobs"].append(info)

    # ---------- reddit ----------
    posts, seen = [], set()
    for rd in (data.get("reddit") or []):
        for p in (rd or {}).get("posts", []):
            if p.get("url") and p["url"] not in seen:
                seen.add(p["url"])
                posts.append(p)
    if posts:
        posts.sort(key=lambda p: str(p.get("date", "")), reverse=True)
        for i, p in enumerate(posts[: config.MAX_REDDIT_POSTS], 1):
            items.append({"item_id": f"p{i}", "signal": "reddit", "title": _cap(p.get("title"), 120),
                          "source_url": p["url"], "date": str(p.get("date", ""))[:10],
                          "text": _cap(f"r/{p.get('subreddit', '?')}: {p.get('title', '')} — {p.get('snippet', '')}")})
        summary["reddit"] = {"posts_collected": len(posts), "posts_used": min(len(posts), config.MAX_REDDIT_POSTS)}

    # ---------- news ----------
    nc = data.get("news_classified")
    risk = []
    if nc:
        arts = nc.get("articles", [])
        ref = None
        try:
            ref = _d(nc["collected_at"]) if nc.get("collected_at") else None
        except ValueError:
            pass

        def age(a):
            try:
                return (ref - _d(a["date"])).days if ref else None
            except (ValueError, KeyError, TypeError):
                return None

        arts = [a for a in arts if age(a) is None or age(a) <= config.NEWS_MAX_AGE_DAYS]
        facts = [a for a in arts if a.get("type") == "reported_fact" and a.get("relevance") in ("high", "medium")]
        for a in facts:
            ag = age(a)
            when = f"published {ag} days before collection" if ag is not None else "publication age unknown"
            items.append({"item_id": a["id"], "signal": "news", "title": _cap(a.get("title"), 140),
                          "source_url": a.get("url"), "date": str(a.get("date", ""))[:10],
                          "text": _cap(f"[{a.get('publisher', '')}] {a.get('title', '')} — {a.get('snippet', '')} "
                                       f"({when}; direction: {a.get('direction')}, topic: {a.get('topic')})", 420)})
        for a in arts:
            if a.get("type") in ("expert_opinion", "speculation") and a.get("relevance") in ("high", "medium"):
                risk.append({"headline": a.get("title"), "type": a["type"], "topic": a.get("topic"),
                             "direction": a.get("direction"), "why_relevant": a.get("why"),
                             "source_url": a.get("url"), "date": str(a.get("date", ""))[:10],
                             "publisher": a.get("publisher")})
        neg = sum(1 for a in facts if a.get("direction") == "negative")
        pos = sum(1 for a in facts if a.get("direction") == "positive")
        summary["news"] = {"articles_collected": len(arts), "relevant_reported_facts": len(facts),
                           "negative_facts": neg, "positive_facts": pos, "risk_context_items": len(risk)}
        if neg >= config.NEWS_NEGATIVE_FACTS:
            flags.append(f"{neg} relevant reported news facts point negative.")

    summary["flags"] = flags
    return items, summary, risk
