"""Answers the chat can give WITHOUT calling Gemini: instant, never overloaded, and always correct because the numbers
come straight from the saved results.
  1. numbers_answer   - counts and comparisons ("which has more gaps, Groww or Eternal?")
  2. profile_answer   - "what is Groww?", "what does Eternal do?"
  3. degraded_answer  - used when Gemini fails: the best-matching saved verdicts, so the user still gets a useful reply
"""
import re

from . import retrieval

DISPLAY = {"groww": "Groww", "eternal": "Eternal"}          # the claims file holds the long legal names
ALIASES = {"groww": ("groww", "billionbrains"), "eternal": ("eternal", "zomato", "blinkit")}

# Short, careful background. Shown with a label, because general knowledge can be out of date.
PROFILES = {
    "groww": "Groww (run by Billionbrains Garage Ventures) is an Indian investing platform. People use its app and website to invest "
             "in stocks and mutual funds, and it offers other products such as futures and options and margin trading. "
             "It earns mainly from broking fees and related services.",
    "eternal": "Eternal is the listed Indian company that owns Zomato, the food delivery and dining app, and Blinkit, a quick-commerce "
               "app that delivers groceries and other items in minutes. It also runs Hyperpure, which supplies restaurants. "
               "Zomato's parent company was renamed Eternal.",
}
GENERAL_NOTE = "(General background, not from the evidence Gap collected, and it may be out of date.)"

METRIC = re.compile(r"\b(gaps?|watch(?:es)?|consistent|scores?|mismatch|insufficient|not enough evidence)\b", re.I)
COMPARE = re.compile(r"\b(more|most|fewer|less|least|higher|lower|worse|worst|better|best|compare|comparison|versus|vs|than|which|both|either)\b", re.I)
COUNT = re.compile(r"\b(how many|number of|count|total)\b", re.I)
PROFILE = re.compile(r"^(what is|what's|what are|what does|who is|tell me about|explain|describe|about)\s+(the\s+)?(?P<name>groww|billionbrains|eternal|zomato|blinkit)"
                     r"(\s+(do|does|company|ltd|limited|business|app|actually do))*\s*\??$", re.I)


def _mentioned(question):
    q = question.lower()
    return [slug for slug, names in ALIASES.items() if any(re.search(rf"\b{n}\b", q) for n in names)]


def _name(o):
    return DISPLAY.get(o["slug"], o["company"])


def _counts_text(o):
    c = o["verdict_counts"]
    return (f"{c['gap']} gap, {c['watch']} watch, {c['consistent']} consistent, "
            f"{c['insufficient_evidence']} not enough evidence")


def _score_text(o):
    if o["gap_score"] is None:
        return "no score yet"
    r = o["gap_score_range"] or {}
    return f"Gap Score {o['gap_score']} (likely range {r.get('low')} to {r.get('high')})"


def numbers_answer(question, overviews, selected):
    """Returns an answer dict or None when the question is not a counting or comparing question."""
    if not (METRIC.search(question) and (COMPARE.search(question) or COUNT.search(question))):
        return None
    if not overviews:
        return None
    named = [o for o in overviews if o["slug"] in _mentioned(question)]
    asked = named if named else overviews
    if len(asked) == 1 and not COMPARE.search(question):
        o = asked[0]
        return {"text": f"{_name(o)}: {_counts_text(o)}. {_score_text(o)}, based on {o['claims_judged']} claims judged."}

    lines = [f"{_name(o)}: {_counts_text(o)}. {_score_text(o)}, based on {o['claims_judged']} claims judged." for o in asked]
    parts = []
    if len(asked) > 1:
        by_gap = sorted(asked, key=lambda o: o["verdict_counts"]["gap"], reverse=True)
        by_watch = sorted(asked, key=lambda o: o["verdict_counts"]["watch"], reverse=True)
        top_gap = by_gap[0]["verdict_counts"]["gap"]
        if top_gap == 0:
            parts.append("Neither company has a 'gap' verdict yet.")
        elif sum(1 for o in asked if o["verdict_counts"]["gap"] == top_gap) > 1:
            parts.append(f"Both have the same number of 'gap' verdicts ({top_gap}).")
        else:
            parts.append(f"{_name(by_gap[0])} has more 'gap' verdicts ({top_gap}).")
        wa, wb = by_watch[0], by_watch[-1]
        if wa["verdict_counts"]["watch"] != wb["verdict_counts"]["watch"]:
            parts.append(f"{_name(wa)} has more 'watch' verdicts ({wa['verdict_counts']['watch']} vs {wb['verdict_counts']['watch']}).")
        scored = [o for o in asked if o["gap_score"] is not None]
        if len(scored) > 1:
            hi, lo = max(scored, key=lambda o: o["gap_score"]), min(scored, key=lambda o: o["gap_score"])
            if hi["gap_score"] != lo["gap_score"]:
                overlap = hi["gap_score_range"] and lo["gap_score_range"] and hi["gap_score_range"]["low"] <= lo["gap_score_range"]["high"]
                parts.append(f"By Gap Score (lower means the web agrees more with management), {_name(hi)} shows more mismatch "
                             f"({hi['gap_score']} vs {lo['gap_score']})" + (", but the ranges overlap, so the difference is small." if overlap else "."))
            else:
                parts.append(f"Their Gap Scores are the same ({hi['gap_score']}).")
    note = "Each score rests on only part of the claims, so treat it as a snapshot, not a ranking of the companies."
    return {"text": " ".join(lines + parts + [note])}


def profile_answer(question, overviews):
    m = PROFILE.match(re.sub(r"[?.!]+$", "", question.strip()) + "?")
    if not m:
        return None
    name = m.group("name").lower()
    slug = next((s for s, names in ALIASES.items() if name in names), None)
    if not slug or slug not in PROFILES:
        return None
    o = next((o for o in overviews if o["slug"] == slug), None)
    extra = f" In Gap, {_name(o)} has {o['claims_judged']} claims judged: {_counts_text(o)}." if o else ""
    return {"text": f"{PROFILES[slug]}{extra}\n\n{GENERAL_NOTE}"}


def degraded_answer(question, res):
    """Gemini is not answering. Give the saved verdicts closest to the question, in plain language."""
    q = set(retrieval._tokens(question))
    scored = []
    for f in res["findings"]:
        text = f"{f['topic']} {f['quote']} {f['explanation']}"
        overlap = len(q & set(retrieval._tokens(text)))
        scored.append((overlap, f))
    scored.sort(key=lambda t: t[0], reverse=True)
    picks = [f for o, f in scored[:2] if o > 0]
    words = {"consistent": "consistent", "watch": "worth watching", "gap": "a gap", "insufficient_evidence": "not enough evidence"}
    if not picks:
        c = res["gap_score"]["counts"]
        return (f"The AI is busy for a moment, so here is the overall picture for {DISPLAY.get(res.get('slug'), res['company'])}: {c['consistent']} claims consistent, "
                f"{c['watch']} worth watching, {c['gap']} with a gap and {c['insufficient_evidence']} without enough evidence. "
                f"Ask again in a minute for a fuller answer.")
    body = " ".join(f"On \"{f['topic']}\", Gap's verdict is {words.get(f['verdict'], f['verdict'])}. {f['explanation']}" for f in picks)
    return f"The AI is busy for a moment, so here is what Gap's analysis says on this. {body}"
