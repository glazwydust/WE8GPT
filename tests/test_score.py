"""Run:  python tests/test_score.py   (from the repo root)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import score

C, W, G, N = "consistent", "watch", "gap", "insufficient_evidence"


def F(*verdicts, items=3):
    """Each judged claim cites `items` distinct evidence items."""
    out = []
    for i, v in enumerate(verdicts):
        ev = [{"item_id": f"c{i}e{k}"} for k in range(items)] if v != N else []
        out.append({"claim_id": i + 1, "verdict": v, "evidence": ev})
    return out


# strength of evidence: 1 item = 0.5, 2 = 0.75, 3 = 0.875, capped at 5 items
assert score._strength(1) == 0.5 and score._strength(3) == 0.875 and score._strength(99) == score._strength(5)

# the posterior mean sits between the plain average and 50 (few claims -> pulled to the middle)
g = score.compute(F(C, C, W, W, N, N, N, N))
assert g["judged_claims"] == 4 and g["total_claims"] == 8 and g["coverage_pct"] == 50
assert 25 <= g["score"] <= 50 and g["raw_score"] == 25, g
assert g["range"]["low"] < g["score"] < g["range"]["high"], g

# more claims judged -> narrower range, the score moves toward the raw average
few = score.compute(F(C, W))
many = score.compute(F(C, W, C, W, C, W, C, W, C, W))
assert (many["range"]["high"] - many["range"]["low"]) < (few["range"]["high"] - few["range"]["low"])

# stronger evidence counts more: a gap on 5 items outweighs a consistent on 1 item
mix = F(G, C)
mix[0]["evidence"] = [{"item_id": f"x{k}"} for k in range(5)]
mix[1]["evidence"] = [{"item_id": "y0"}]
assert score.compute(mix)["raw_score"] > 50
mix2 = F(G, C)
mix2[0]["evidence"] = [{"item_id": "x0"}]
mix2[1]["evidence"] = [{"item_id": f"y{k}"} for k in range(5)]
assert score.compute(mix2)["raw_score"] < 50

# ordering: all consistent < mixed < all gaps
assert score.compute(F(C, C, C, C))["score"] < score.compute(F(C, W, G, C))["score"] < score.compute(F(G, G, G, G))["score"]
assert score.compute(F(G, G, G, G))["score"] < 100          # never claims certainty from 4 claims
assert score.compute(F(C, C, C, C))["score"] > 0

# nothing judged: no score
assert score.compute(F(N, N, N))["score"] is None
# unknown verdict is not judged
assert score.compute(F("nonsense", C))["counts"]["insufficient_evidence"] == 1

# stability: removing any one claim from 4 moves the score by a known, bounded amount
st = score.compute(F(C, C, W, W))
assert st["max_single_claim_swing"] is not None and 0 <= st["max_single_claim_swing"] < 30, st

# importance weights: a heavier gap claim pulls the score up
base = score.compute(F(G, C))["score"]
heavy = score.compute(F(G, C), weights={1: 3, 2: 1})["score"]
assert heavy > base
assert score.compute(F(G, C), weights={1: -5, 2: "x"})["score"] == base      # bad weights fall back to 1

# rounding matches the website (half rounds up)
assert score._round(12.5) == 13 and score._round(24.4) == 24

# the credible interval of Beta(1,1) is about 5% to 95%
lo, hi = score._interval(1, 1)
assert abs(lo - 0.05) < 0.01 and abs(hi - 0.95) < 0.01

for name, fs in (("Groww-like", F(C, C, W, W, N, N, N, N)), ("Eternal-like", F(C, C, C, W, N, N, N, N))):
    r = score.compute(fs)
    print(f"{name}: score {r['score']}  range {r['range']['low']}-{r['range']['high']}  raw {r['raw_score']}  "
          f"confidence {r['confidence']}  one-claim swing {r['max_single_claim_swing']}  label {r['label']} (certain: {r['label_is_certain']})")
print("all score tests passed")
