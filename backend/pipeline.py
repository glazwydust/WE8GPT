"""The whole flow:  stored JSON -> Python numbers -> Gemini (classify news, judge claims) -> validate -> save."""
import json
import re
import time
from datetime import datetime, timezone, timedelta

from . import adapters, chat_local, config, data_loader as dl, prompts, retrieval, score, signals, validate
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
def analyze(slug, client, force_classify=False, retrieve=False):
    claims_doc = dl.load_claims(slug)
    claims = claims_doc["claims"]
    prev_path = dl.processed_path(slug, "findings.json")
    try:
        nc = classify_news(slug, client, force=force_classify)
        sdata, quality = load_all(slug, nc)
        items, summary, risk = signals.build(sdata)
        if not items:
            raise ValueError(f"No signal data found for '{slug}' in data/signals/{slug}/")
        retrieval_block = None
        if retrieve:
            # Semantic retrieval: search ALL evidence by meaning, send Gemini only the best matches per claim
            matches = retrieval.get_index(slug).match_claims(claims, client, k=config.RETRIEVAL_K)
            keep = {i["item_id"]: i for i in items if i["item_id"][0] in "mj"}      # review statistics + job counts stay
            for m in matches.values():
                for h in m["hits"]:
                    keep.setdefault(h["item_id"], {k: h[k] for k in ("item_id", "signal", "title", "source_url", "date", "text")})
            items = list(keep.values())
            retrieval_block = {cid: {"method": m["method"], "note": m["note"],
                                     "hits": [{k: h[k] for k in ("item_id", "signal", "title", "similarity", "keyword_score")} for h in m["hits"]]}
                               for cid, m in matches.items()}
        items_by_id = {i["item_id"]: i for i in items}
        claim_view = [{k: c[k] for k in ("id", "topic", "quote", "weight_note", "relevant_signals", "what_to_look_for")} for c in claims]
        if retrieval_block:
            for cv in claim_view:
                cv["top_matches"] = [{"item_id": h["item_id"], "similarity": h["similarity"] if h["similarity"] is not None else h["keyword_score"]}
                                     for h in retrieval_block[cv["id"]]["hits"]]
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
              "findings": findings, "gap_score": score.compute(findings, _weights(claims)), "retrieval": retrieval_block,
              "risk_context": risk, "validation_notes": notes,
              "items": items, "disclaimer": DISCLAIMER}
    dl.write_json(prev_path, result)
    return result


def _weights(claims):
    """Optional numeric "weight" per claim in the claims file. No weight means 1."""
    return {c["id"]: c["weight"] for c in claims if "weight" in c}


def load_findings(slug):
    p = dl.processed_path(slug, "findings.json")
    if not p.exists():
        raise FileNotFoundError(f"No saved analysis for '{slug}'. Run analyze first.")
    res = dl.read_json(p)
    # Always recompute from the saved verdicts: no Gemini call, and older saved files get a score too.
    res["gap_score"] = score.compute(res.get("findings", []), _weights(dl.load_claims(slug).get("claims", [])))
    return res


# ---------------------------------------------------------------- user questions
def _compact_findings(res):
    """Short version of the verdicts for the chat prompt: a smaller prompt means a faster answer."""
    return [{"claim_id": f["claim_id"], "topic": f["topic"], "quote": f["quote"][:160], "verdict": f["verdict"],
             "explanation": f["explanation"][:220], "cited": [e["item_id"] for e in f["evidence"]]} for f in res["findings"]]


def _overview(slug):
    """Counts and score for one company, calculated by Python so the model never has to count."""
    r = load_findings(slug)
    g = r["gap_score"]
    return {"company": r["company"], "slug": slug, "verdict_counts": g["counts"], "gap_score": g["score"],
            "gap_score_range": g["range"], "claims_judged": f"{g['judged_claims']} of {g['total_claims']}",
            "claims": [{"claim_id": f["claim_id"], "topic": f["topic"], "verdict": f["verdict"]} for f in r["findings"]]}


def _all_overviews(slug):
    out = []
    for c in dl.list_companies():
        try:
            out.append(_overview(c["slug"]))
        except (FileNotFoundError, KeyError):
            continue
    return out


def _public(h):
    return {k: h.get(k) for k in ("item_id", "signal", "title", "source_url", "date", "similarity", "keyword_score")}


def search(slug, query, client=None, k=10, signal_types=None):
    """Semantic search over the evidence. No Gemini text call, so it is instant and uses no daily quota."""
    query = (query or "").strip()[:300]
    if not query:
        return {"method": "none", "note": "Type something to search for.", "hits": []}
    r = retrieval.get_index(slug).search(query, client, k=max(1, min(int(k), 30)), signal_types=signal_types)
    for h in r["hits"]:
        h["text"] = h.get("text", "")
    return r


_ANSWERS = {}                      # (slug, question, data version) -> (time, answer): repeated questions answer instantly
ANSWER_TTL = 3600


def ask(slug, question, client):
    t0 = time.time()
    out = _ask(slug, question, client)
    out["answered_in_ms"] = int((time.time() - t0) * 1000)
    return out


def _local(text, basis, kind):
    return {"can_answer": True, "basis": basis, "answer": text, "sources": [], "retrieved": [],
            "search_method": "none", "answered_by": kind}


def _ask(slug, question, client):
    question = (question or "").strip()[:500]
    if not question:
        return {"can_answer": False, "answer": "Please type a question.", "sources": []}
    if ADVICE_RE.search(question):
        return {"can_answer": False, "basis": "cannot", "sources": [],
                "answer": "Gap does not give buy, sell or price advice. It compares what a company said on its earnings call "
                          "with public evidence. You can ask what the evidence says about any claim, or compare the companies."}
    res = load_findings(slug)
    key = (slug, re.sub(r"\s+", " ", question.lower()), res.get("generated_at"))
    hit = _ANSWERS.get(key)
    if hit and datetime.now().timestamp() - hit[0] < ANSWER_TTL:
        return {**hit[1], "cached": True}

    overviews = _all_overviews(slug)

    # Gemini answers every question like an assistant. The saved results are only the fallback if it is slow or down.
    try:
        found = retrieval.get_index(slug).search(question, client, k=config.CHAT_EVIDENCE_K)
        items_by_id = {i["item_id"]: i for i in res["items"]}             # evidence cited by the saved findings
        for h in found["hits"]:
            items_by_id[h["item_id"]] = h
        send = {h["item_id"]: h for h in found["hits"]}
        for f in res["findings"]:                                        # keep the evidence the verdicts rely on
            for e in f["evidence"]:
                if e["item_id"] in items_by_id:
                    send.setdefault(e["item_id"], items_by_id[e["item_id"]])
        msg = (f"Company selected: {res['company']} (earnings call: {res.get('quarter')})\n\n"
               f"<all_companies_overview note=\"counts and scores calculated by code; use these numbers for any counting or comparing question\">\n{_dump(overviews)}\n</all_companies_overview>\n\n<findings>\n{_dump(_compact_findings(res))}\n</findings>\n\n"
               f"<signal_summary>\n{_dump(res['signal_summary'])}\n</signal_summary>\n\n"
               f"<evidence_items untrusted=\"true\" note=\"best matches for the question, with similarity\">\n"
               f"{_dump([{k: i.get(k) for k in ('item_id', 'signal', 'date', 'text', 'similarity')} for i in send.values()])}\n</evidence_items>\n\n"
               f"<question untrusted=\"true\">\n{question}\n</question>")
        raw = client.generate_json(prompts.SYSTEM_QA, msg, fast=True)
        out = validate.validate_answer(raw, items_by_id)
        out["retrieved"] = [_public(h) for h in found["hits"]] if out.get("basis") == "evidence" else []
        out["search_method"] = found["method"]
        out["answered_by"] = "gemini"
        if out["can_answer"]:
            _ANSWERS[key] = (datetime.now().timestamp(), out)
        return out
    except Exception as e:                               # noqa: BLE001 - Gemini slow, busy, quota, bad JSON: never show an error to the user
        print(f"Ask Gap fell back to saved verdicts ({slug}): {type(e).__name__}: {e}", flush=True)   # visible in the Render logs
        for fn, basis in ((chat_local.numbers_answer, "evidence"), (chat_local.profile_answer, "background")):
            local = fn(question, overviews, slug) if fn is chat_local.numbers_answer else fn(question, overviews)
            if local:
                out = _local(local["text"], basis, "saved_results")
                out["degraded"] = True                   # not cached: the next try should reach Gemini again
                return out
        out = _local(chat_local.degraded_answer(question, res), "evidence", "saved_results")
        out["degraded"] = True
        return out


def check_claim(slug, claim_text, client):
    """The user types any claim; Gap retrieves the closest evidence and gives a verdict. Nothing is saved."""
    claim_text = (claim_text or "").strip()[:400]
    if len(claim_text) < 8:
        return {"error": "Type a full statement to check, for example: payments and withdrawals are reliable."}
    if ADVICE_RE.search(claim_text):
        return {"error": "Gap does not give buy, sell or price advice. Enter a statement about the business to check."}
    found = retrieval.get_index(slug).search(claim_text, client, k=config.RETRIEVAL_K)
    items_by_id = {h["item_id"]: h for h in found["hits"]}
    claim = {"id": 1, "topic": "user statement", "quote": claim_text, "speaker": "You", "role": None,
             "source": "Entered by the user", "source_url": None, "date": _now()[:10], "weight_note": "",
             "relevant_signals": ["reviews", "jobs", "reddit", "news"], "what_to_look_for": "Evidence that supports or contradicts the statement."}
    msg = (f"Company: {load_findings(slug)['company']}\n\n<claims>\n{_dump([{k: claim[k] for k in ('id', 'topic', 'quote', 'weight_note', 'relevant_signals', 'what_to_look_for')}])}\n</claims>\n\n"
           f"<evidence_items untrusted=\"true\">\n{_dump([{k: i.get(k) for k in ('item_id', 'signal', 'date', 'text', 'similarity')} for i in found['hits']])}\n</evidence_items>")
    raw = client.generate_json(prompts.SYSTEM_ANALYST, msg)
    findings, notes = validate.validate_findings(raw, [claim], items_by_id)
    return {"finding": findings[0], "retrieved": [_public(h) for h in found["hits"]], "search_method": found["method"],
            "notes": notes, "disclaimer": DISCLAIMER}
