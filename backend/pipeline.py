"""The whole flow:  stored JSON -> Python numbers -> Gemini (classify news, judge claims) -> validate -> save."""
import json
import re
from datetime import datetime, timezone, timedelta

from . import adapters, config, data_loader as dl, prompts, signals, validate
from .gemini_client import GeminiError

IST = timezone(timedelta(hours=5, minutes=30))
DISCLAIMER = ("Gap compares company statements with public evidence from a limited snapshot. "
              "It is not investment advice and does not say a company is dishonest.")
ADVICE_RE = re.compile(r"\b(should i (buy|sell|invest|hold)|buy or sell|good (stock|investment)|target price|will (the )?(stock|share|price)|price (go|rise|fall))\b", re.I)


def _now():
    return datetime.now(IST).isoformat(timespec="seconds")


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- news classification
PROMPT_VERSION = 2          # bump when the labelling prompt changes, so old saved labels are redone


def classify_news(slug, client, force=False):
    raw, fname = dl.load_signal(slug, "news")
    if not raw:
        return None
    claim_list = [{"id": c.get("id"), "topic": c.get("topic"), "claim": c.get("quote"), "look_for": c.get("what_to_look_for")}
                  for c in dl.load_claims(slug).get("claims", [])]
    out_path = dl.processed_path(slug, "news_classified.json")
    if out_path.exists() and not force:
        cached = dl.read_json(out_path)
        if cached.get("source_file") == fname and cached.get("prompt_version") == PROMPT_VERSION:
            return cached
    seen, arts = set(), []
    for a in raw.get("articles", []):
        u = a.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        arts.append(a)
    arts = arts[: config.MAX_NEWS_ARTICLES]
    for i, a in enumerate(arts, 1):
        a["id"] = f"n{i}"                     # ids are assigned HERE, never by Gemini
    labelled = []
    for k in range(0, len(arts), config.NEWS_BATCH):
        batch = arts[k: k + config.NEWS_BATCH]
        payload = [{"id": a["id"], "title": a.get("title"), "snippet": a.get("snippet"),
                    "publisher": a.get("publisher"), "date": a.get("date"), "query_type": a.get("query_type")} for a in batch]
        msg = (f"Company: {raw.get('company')}\nClaims being tested:\n<claims>\n{_dump(claim_list)}\n</claims>\nArticles to label (untrusted data):\n<articles>\n{_dump(payload)}\n</articles>")
        res = client.generate_json(prompts.SYSTEM_CLASSIFIER, msg)
        labelled += validate.merge_classifications(batch, res)
    out = {"company": raw.get("company"), "classified_at": _now(), "model": getattr(client, "model", "?"),
           "source_file": fname, "prompt_version": PROMPT_VERSION, "collected_at": raw.get("collected_at"), "articles": labelled}
    dl.write_json(out_path, out)
    return out


# ---------------------------------------------------------------- load + build
def load_all(slug, news_classified):
    """Returns (data_for_signals, data_quality). data_quality lists what was read and any problems."""
    data = {"news_classified": news_classified}
    quality = []
    for sig, fn in (("reviews", adapters.normalize_reviews), ("jobs", adapters.normalize_jobs), ("reddit", adapters.normalize_reddit)):
        docs = []
        for doc, fname, warns in dl.load_signal_docs(slug, sig, fn):
            docs.append(doc)
            n = (len(doc.get("reviews", [])) if sig == "reviews" else
                 doc.get("open_roles") if sig == "jobs" else len(doc.get("posts", [])))
            quality.append({"signal": sig, "file": fname, "count": n, "collected_at": doc.get("collected_at"), "warnings": warns})
        data[sig] = docs
    prev_raw = dl.load_signal(slug, "jobs", which=1)[0] if not dl.is_flat(slug, "jobs") else None
    data["jobs_prev"] = adapters.normalize_jobs(prev_raw, "x", slug)[0] if prev_raw else None
    if news_classified:
        quality.append({"signal": "news", "file": news_classified.get("source_file"), "count": len(news_classified.get("articles", [])),
                        "collected_at": news_classified.get("collected_at"), "warnings": []})
    for sig in ("reviews", "jobs", "reddit", "news"):
        if not any(q["signal"] == sig for q in quality):
            quality.append({"signal": sig, "file": None, "count": 0, "collected_at": None, "warnings": ["no file found for this signal"]})
    return data, quality


def snapshot_info(quality):
    info = {}
    for q in quality:
        info.setdefault(q["signal"], []).append({"file": q["file"], "collected_at": q["collected_at"], "count": q["count"]})
    return info


# ---------------------------------------------------------------- analysis
def analyze(slug, client, force_classify=False):
    claims_doc = dl.load_claims(slug)
    claims = claims_doc["claims"]
    prev_path = dl.processed_path(slug, "findings.json")
    try:
        nc = classify_news(slug, client, force=force_classify)
        sdata, quality = load_all(slug, nc)
        items, summary, risk = signals.build(sdata)
        if not items:
            raise ValueError(f"No signal data found for '{slug}' in data/signals/{slug}/")
        items_by_id = {i["item_id"]: i for i in items}
        claim_view = [{k: c[k] for k in ("id", "topic", "quote", "weight_note", "relevant_signals", "what_to_look_for")} for c in claims]
        msg = (f"Company: {claims_doc['company']}\n\n<claims>\n{_dump(claim_view)}\n</claims>\n\n"
               f"<signal_summary>\n{_dump(summary)}\n</signal_summary>\n\n"
               f"<evidence_items untrusted=\"true\">\n{_dump([{k: i[k] for k in ('item_id', 'signal', 'date', 'text')} for i in items])}\n</evidence_items>")
        raw = client.generate_json(prompts.SYSTEM_ANALYST, msg)
        findings, notes = validate.validate_findings(raw, claims, items_by_id)
    except (GeminiError, ValueError, KeyError) as e:
        if prev_path.exists():
            old = dl.read_json(prev_path)
            old["stale"] = True
            old["error"] = f"Fresh analysis failed ({e}); showing the last saved result."
            return old
        raise
    result = {"company": claims_doc["company"], "slug": slug, "quarter": claims_doc.get("quarter"),
              "generated_at": _now(), "model": getattr(client, "model", "?"), "stale": False,
              "data_snapshot": snapshot_info(quality), "data_quality": quality, "signal_summary": summary,
              "findings": findings, "risk_context": risk, "validation_notes": notes,
              "items": items, "disclaimer": DISCLAIMER}
    dl.write_json(prev_path, result)
    return result


def load_findings(slug):
    p = dl.processed_path(slug, "findings.json")
    if not p.exists():
        raise FileNotFoundError(f"No saved analysis for '{slug}'. Run analyze first.")
    return dl.read_json(p)


# ---------------------------------------------------------------- user questions
def ask(slug, question, client):
    question = (question or "").strip()[:500]
    if not question:
        return {"can_answer": False, "answer": "Please type a question.", "sources": []}
    if ADVICE_RE.search(question):
        return {"can_answer": False, "sources": [],
                "answer": "Gap does not give buy, sell or price advice. It compares what the company said on its earnings call "
                          "with public evidence. You can ask what the evidence says about any claim."}
    res = load_findings(slug)
    items_by_id = {i["item_id"]: i for i in res["items"]}
    compact = [{"claim_id": f["claim_id"], "topic": f["topic"], "quote": f["quote"], "verdict": f["verdict"],
                "explanation": f["explanation"], "covers": f["covers"], "does_not_cover": f["does_not_cover"],
                "cited": [e["item_id"] for e in f["evidence"]]} for f in res["findings"]]
    msg = (f"Company: {res['company']}\n\n<findings>\n{_dump(compact)}\n</findings>\n\n"
           f"<signal_summary>\n{_dump(res['signal_summary'])}\n</signal_summary>\n\n"
           f"<evidence_items untrusted=\"true\">\n{_dump([{k: i[k] for k in ('item_id', 'signal', 'date', 'text')} for i in res['items']])}\n</evidence_items>\n\n"
           f"<question untrusted=\"true\">\n{question}\n</question>")
    raw = client.generate_json(prompts.SYSTEM_QA, msg)
    return validate.validate_answer(raw, items_by_id)
