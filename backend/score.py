"""Gap Score, version 2: a small Bayesian score. Pure Python, no Gemini, no extra packages, same answer every run.

Plain-language idea
  Every judged claim has a mismatch value: consistent = 0, watch = 0.5, gap = 1.
  A claim counts MORE when it rests on more evidence, and when it matters more (optional "weight" in the claims file).
  Claims with not enough evidence are not judged and carry no weight.
  We do not just average. We treat the judged claims as a small sample and ask:
  "how much mismatch is there, and how sure can we be?"  The answer is a score AND a range.

Maths
  For each judged claim i:   m_i = 0 / 0.5 / 1        (mismatch)
                             s_i = 1 - 0.5 ** n_i     (evidence strength, n_i = distinct cited items, capped at 5)
                             w_i = importance_i * s_i (importance defaults to 1)
  S = sum(w_i * m_i)      W = sum(w_i)
  Posterior for the overall mismatch rate p:  Beta(1 + S, 1 + W - S)      (uniform prior, so few claims -> wide range)
  Gap Score  = 100 * posterior mean = 100 * (1 + S) / (2 + W)
  Range      = 5th to 95th percentile of that Beta distribution (90% credible interval)
  Raw score  = 100 * S / W   (the plain weighted average, shown for transparency)
  Stability  = the most the score moves if any ONE judged claim is removed (leave-one-out).

Lower is better: the web agrees with management.
"""
import math

MISMATCH = {"consistent": 0.0, "watch": 0.5, "gap": 1.0}
EVIDENCE_CAP = 5
GOOD, MIXED = 30, 60                   # label cut-offs: our own choice, not an official standard
GRID = 2000


def _round(x):
    """Round half up, like JavaScript Math.round (Python's round() turns 12.5 into 12)."""
    return int(x + 0.5)


def _label(score):
    if score <= GOOD:
        return "Mostly consistent"
    if score <= MIXED:
        return "Mixed picture"
    return "Gaps worth reviewing"


def _strength(n_items):
    n = max(1, min(EVIDENCE_CAP, n_items))
    return 1 - 0.5 ** n


def _posterior(S, W):
    return 1 + S, 1 + W - S


def _interval(a, b, lo=0.05, hi=0.95):
    """Credible interval of Beta(a, b) by deterministic numerical integration (no scipy needed)."""
    xs = [(i + 0.5) / GRID for i in range(GRID)]
    logp = [(a - 1) * math.log(x) + (b - 1) * math.log(1 - x) for x in xs]
    m = max(logp)
    pdf = [math.exp(v - m) for v in logp]
    total = sum(pdf)
    acc, out = 0.0, []
    targets = [lo, hi]
    for x, p in zip(xs, pdf):
        acc += p / total
        while targets and acc >= targets[0]:
            out.append(x)
            targets.pop(0)
    while len(out) < 2:
        out.append(1.0)
    return out[0], out[1]


def _score_from(S, W):
    a, b = _posterior(S, W)
    return 100 * a / (a + b)


def compute(findings, weights=None):
    """findings: validated list from validate_findings (claim_id, verdict, evidence[]).
    weights: optional {claim_id: importance}. Missing or invalid importance counts as 1."""
    weights = weights or {}
    counts = {"consistent": 0, "watch": 0, "gap": 0, "insufficient_evidence": 0}
    judged = []                                   # (claim_id, m, w)
    for f in findings:
        v = f.get("verdict")
        v = v if v in counts else "insufficient_evidence"
        counts[v] += 1
        if v in MISMATCH:
            imp = weights.get(f.get("claim_id"), 1)
            imp = imp if isinstance(imp, (int, float)) and imp > 0 else 1
            n = len({e.get("item_id") for e in (f.get("evidence") or []) if isinstance(e, dict)})
            judged.append({"claim_id": f.get("claim_id"), "verdict": v, "m": MISMATCH[v],
                           "evidence_items": n, "strength": round(_strength(n), 2),
                           "w": imp * _strength(n)})
    total = sum(counts.values())
    n_judged = len(judged)
    coverage = _round(100 * n_judged / total) if total else 0

    if not judged:
        return {"score": None, "label": "Not enough evidence to score", "judged_claims": 0, "total_claims": total,
                "coverage_pct": 0, "confidence": "low", "counts": counts, "range": None,
                "method": METHOD, "caveat": CAVEAT}

    S = sum(j["w"] * j["m"] for j in judged)
    W = sum(j["w"] for j in judged)
    score = _score_from(S, W)
    a, b = _posterior(S, W)
    lo, hi = _interval(a, b)
    lo, hi = 100 * lo, 100 * hi
    width = hi - lo

    # stability: how far can ONE claim move the score?
    swings = []
    for j in judged:
        s2, w2 = S - j["w"] * j["m"], W - j["w"]
        swings.append(abs(_score_from(s2, w2) - score))
    swing = max(swings) if len(judged) > 1 else None

    confidence = "high" if width <= 30 else "medium" if width <= 50 else "low"
    certain = _label(lo) == _label(hi)
    return {"score": _round(score), "score_exact": round(score, 1), "label": _label(score),
            "label_is_certain": certain,
            "range": {"low": _round(lo), "high": _round(hi), "level": "90%",
                      "meaning": "We are 90% sure the true mismatch score lies in this range."},
            "raw_score": _round(100 * S / W) if W else None,
            "confidence": confidence,
            "judged_claims": n_judged, "total_claims": total, "coverage_pct": coverage,
            "max_single_claim_swing": _round(swing) if swing is not None else None,
            "counts": counts, "per_claim": [{k: j[k] for k in ("claim_id", "verdict", "evidence_items", "strength")} for j in judged],
            "method": METHOD, "caveat": CAVEAT if (confidence != "high" or not certain) else ""}


METHOD = ("Each judged claim scores consistent = 0, watch = 0.5, gap = 1. Claims backed by more evidence count more. "
          "We treat the judged claims as a small sample, so the score comes with a 90% range that is wide when there "
          "are few claims. Claims with not enough evidence are left out and shown as coverage.")
CAVEAT = ("Based on only part of the claims, so read the range, not just the number. "
          "It measures mismatch with the evidence we collected. It does not say a company is dishonest "
          "and it is not investment advice.")
