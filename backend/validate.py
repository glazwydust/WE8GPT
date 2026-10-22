"""Everything Gemini returns is checked here before anyone sees it."""
VERDICTS = {"consistent", "watch", "gap", "insufficient_evidence"}
NEWS_TYPES = {"reported_fact", "expert_opinion", "speculation"}
TOPICS = {"regulation", "outage_tech", "mtf_margin", "fees_pricing", "competition", "product_launch",
          "financials", "legal_enforcement", "macro_market", "other"}
DIRECTIONS = {"positive", "negative", "neutral", "mixed"}
RELEVANCE = {"high", "medium", "low", "none"}


def merge_classifications(articles, raw):
    """articles carry backend ids (n1..). Merge Gemini labels back BY ID; never trust order."""
    by_id = {c.get("id"): c for c in (raw or {}).get("classifications", []) if isinstance(c, dict)}
    out = []
    for a in articles:
        c = by_id.get(a["id"], {})
        t = c.get("type") if c.get("type") in NEWS_TYPES else "unclassified"
        out.append({**a,
                    "type": t,
                    "topic": c.get("topic") if c.get("topic") in TOPICS else "other",
                    "direction": c.get("direction") if c.get("direction") in DIRECTIONS else "neutral",
                    "relevance": c.get("relevance") if c.get("relevance") in RELEVANCE and t != "unclassified" else "none",
                    "why": str(c.get("why", ""))[:200]})
    return out


def validate_findings(raw, claims, items_by_id):
    """Return (findings, notes). Claim text always comes from the claims file, evidence urls/dates from the items."""
    notes = []
    got = {}
    for f in (raw or {}).get("findings", []):
        if isinstance(f, dict) and isinstance(f.get("claim_id"), int):
            got[f["claim_id"]] = f
    findings = []
    for c in claims:
        f = got.get(c["id"])
        ev_out, n_dropped = [], 0
        verdict = "insufficient_evidence"
        expl = "Gemini returned no finding for this claim."
        covers = dn = ""
        if f:
            verdict = f.get("verdict") if f.get("verdict") in VERDICTS else "insufficient_evidence"
            expl = str(f.get("explanation", ""))[:600]
            covers = str(f.get("covers", ""))[:300]
            dn = str(f.get("does_not_cover", ""))[:300]
            seen = set()
            for e in f.get("evidence", []) or []:
                iid = e.get("item_id") if isinstance(e, dict) else None
                it = items_by_id.get(iid)
                if not it or iid in seen:
                    n_dropped += 1
                    continue
                seen.add(iid)
                ev_out.append({"item_id": iid, "signal": it["signal"], "title": it["title"],
                               "source_url": it["source_url"], "date": it["date"],
                               "what_it_shows": str(e.get("what_it_shows", ""))[:250]})
        fnotes = []
        if n_dropped:
            fnotes.append(f"{n_dropped} cited item(s) were not in the supplied data and were removed.")
        types = {e["signal"] for e in ev_out}
        if verdict != "insufficient_evidence" and not ev_out:
            fnotes.append(f"Verdict '{verdict}' changed to insufficient_evidence: no valid evidence cited.")
            verdict = "insufficient_evidence"
        if verdict == "gap" and len(types) < 2:
            fnotes.append("Verdict 'gap' lowered to 'watch': a gap needs evidence from at least two different signal types.")
            verdict = "watch"
        findings.append({
            "claim_id": c["id"], "topic": c["topic"], "quote": c["quote"], "speaker": c["speaker"],
            "role": c.get("role"), "source": c["source"], "source_url": c.get("source_url"), "date": c["date"],
            "weight_note": c.get("weight_note"),
            "verdict": verdict, "explanation": expl, "covers": covers, "does_not_cover": dn,
            "evidence": ev_out, "signal_types": sorted(types), "notes": fnotes,
        })
        notes += [f"claim {c['id']}: {n}" for n in fnotes]
    return findings, notes


BASES = {"evidence", "background", "about_gap", "cannot"}
BACKGROUND_NOTE = "(General background, not from the evidence Gap collected, and it may be out of date.)"


def validate_answer(raw, items_by_id):
    raw = raw if isinstance(raw, dict) else {}
    basis = raw.get("basis") if raw.get("basis") in BASES else "evidence"
    src, seen = [], set()
    for iid in raw.get("used_item_ids", []) or []:
        it = items_by_id.get(iid)
        if it and iid not in seen:
            seen.add(iid)
            src.append({"item_id": iid, "signal": it["signal"], "title": it["title"],
                        "source_url": it["source_url"], "date": it["date"]})
    can = bool(raw.get("can_answer")) and bool(raw.get("answer"))
    if not can:
        return {"can_answer": False, "basis": "cannot", "sources": [],
                "answer": str(raw.get("answer", ""))[:400] or "The saved data does not cover that."}
    answer = str(raw.get("answer", ""))[:1200]
    if basis == "about_gap":
        src = []
    if basis == "background":
        src = []                                           # background answers cite nothing: be honest about that
        if "general background" not in answer.lower():
            answer += "\n\n" + BACKGROUND_NOTE
    return {"can_answer": True, "basis": basis, "answer": answer, "sources": src}
