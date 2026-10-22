"""Retrieval tests with FAKE data and a FAKE Gemini (including fake embeddings). No network, no key.
Run from the repo root:   python -m tests.test_retrieval"""
import json, re, shutil, tempfile
from datetime import date, timedelta
from pathlib import Path
from backend import config, pipeline, retrieval, data_loader as dl

tmp = Path(tempfile.mkdtemp())
config.DATA = tmp; config.SIGNALS_DIR = tmp / "signals"; config.PROCESSED_DIR = tmp / "processed"; config.CLAIMS_DIR = tmp / "claims"
shutil.copytree(Path("data/claims"), config.CLAIMS_DIR)
(config.SIGNALS_DIR / "groww").mkdir(parents=True)

TEXTS = ["cannot take my money out, payout stuck for days", "withdrawal pending since monday", "love the new chart screen",
         "app crashes when I open the portfolio", "customer care never replies to my ticket", "great app very smooth",
         "brokerage charges are hidden and confusing", "nice interface", "login otp not coming", "funds stuck, no refund",
         "good for beginners", "support is useless, no response"] * 3          # 36 distinct-ish reviews
revs = []
for i, t in enumerate(TEXTS):
    revs.append({"rating": 1 if any(w in t for w in ("stuck", "pending", "crash", "never", "hidden", "otp", "useless")) else 5,
                 "text": t + f" #{i}", "date": (date(2026, 10, 18) - timedelta(days=i % 20)).isoformat()})
json.dump({"app_name": "Groww (FAKE)", "url": "https://play.example/groww", "collected_at": "2026-10-18T10:00:00+05:30", "reviews": revs},
          open(tmp / "groww_playstore.json", "w"))
json.dump({"collected_at": "2026-10-18T10:00:00+05:30", "open_roles": 40, "url": "https://fake.example/careers"}, open(tmp / "groww_careers.json", "w"))
json.dump({"collected_at": "2026-10-19T09:00:00+05:30", "results": [
    {"title": "Money stuck for a week on Groww", "selftext": "payout never arrived", "subreddit": "r/IndiaInvestments", "permalink": "/r/fake/comments/1", "created_utc": 1760500000},
    {"title": "Best mutual funds this year", "selftext": "returns discussion", "subreddit": "r/IndiaInvestments", "permalink": "/r/fake/comments/2", "created_utc": 1760400000}]},
    open(tmp / "groww_reddit.json", "w"))

# --- a tiny FAKE "meaning" embedder: words with similar meaning share a dimension, so synonyms match
GROUPS = [("withdraw", "payout", "money", "funds", "take", "stuck", "pending", "refund"),
          ("crash", "freeze", "hang", "slow", "glitch"), ("support", "care", "ticket", "reply", "response", "replies"),
          ("charge", "brokerage", "fee", "hidden"), ("love", "great", "nice", "smooth", "good", "interface", "chart")]


def fake_vec(text):
    t = text.lower()
    v = [0.0] * config.EMBED_DIM
    for g, words in enumerate(GROUPS):
        v[g] = float(sum(t.count(w) for w in words))
    v[100] = 0.05                                    # tiny constant so no vector is all zeros
    return v


class FakeGemini:
    model = "fake"
    embed_calls = 0
    fail_embed = False
    prompts = []

    def embed(self, texts, task="RETRIEVAL_DOCUMENT"):
        if self.fail_embed:
            raise RuntimeError("embedding service down")
        FakeGemini.embed_calls += 1
        return [fake_vec(t) for t in texts]

    def generate_json(self, system, user, fast=False):
        FakeGemini.prompts.append(user)
        if "label news articles" in system:
            return {"classifications": []}
        if "analysis engine" in system:
            claims = json.loads(re.search(r"<claims>\n(.*?)\n</claims>", user, re.S).group(1))
            ids = re.findall(r'"item_id": "([^"]+)"', re.search(r"<evidence_items.*?>\n(.*)\n</evidence_items>", user, re.S).group(1))
            f = []
            for c in claims:
                ev = [{"item_id": ids[0], "what_it_shows": "x"}] if ids else []
                f.append({"claim_id": c["id"], "verdict": "watch" if ev else "insufficient_evidence", "evidence": ev,
                          "explanation": "e", "covers": "c", "does_not_cover": "d"})
            return {"findings": f}
        ids = re.findall(r'"item_id": "([^"]+)"', user)
        return {"can_answer": True, "answer": "Money stuck reports found.", "used_item_ids": ids[:1] + ["bogus"]}


c = FakeGemini()

# 1. the pool is wider than what the analysis used to see (all reviews, all Reddit posts)
from backend import signals, adapters
pool = retrieval.build_pool("groww")
base_items, _, _ = signals.build(pipeline.load_all("groww", None)[0])
assert len(pool) > len(base_items) + 10, (len(pool), len(base_items))
assert len({i["item_id"] for i in pool}) == len(pool)                    # ids are unique
assert sum(1 for i in pool if i["signal"] == "reddit") == 2              # both Reddit posts, not just the capped sample

# 2. keyword search only (no vectors saved yet, no client)
idx = retrieval.get_index("groww")
assert not idx.has_vectors
r = idx.search("withdrawal stuck", None, k=5)
assert r["method"] == "keyword" and r["hits"] and "stuck" in r["hits"][0]["text"] or "withdraw" in r["hits"][0]["text"]
assert all(h["similarity"] is None for h in r["hits"])
assert idx.search("zzzz qqqq", None)["hits"] == []                       # nothing related: returns nothing, not junk

# 3. save vectors once; the second run embeds nothing; a changed document embeds only itself
info = retrieval.build_vectors("groww", c)
assert info["newly_embedded"] == info["documents"] > 0
calls = FakeGemini.embed_calls
assert retrieval.build_vectors("groww", c)["newly_embedded"] == 0 and FakeGemini.embed_calls == calls
cache = dl.read_json(dl.processed_path("groww", "embeddings.json"))
assert cache["dim"] == config.EMBED_DIM and all(len(v["v"]) == config.EMBED_DIM for v in cache["docs"].values())

# 4. meaning search finds evidence the keywords miss: "payout delayed" never appears in the reviews as such
idx = retrieval.get_index("groww")
assert idx.has_vectors
kw_only = idx.search("take my funds out", None, k=5)                     # words differ from the reviews except 'funds'/'take'
mean = idx.search("take my funds out", c, k=5)
assert mean["method"] == "meaning+keyword" and mean["hits"][0]["similarity"] is not None
assert any("withdraw" in h["text"] or "payout" in h["text"] or "stuck" in h["text"] for h in mean["hits"])
assert all(-1.01 <= h["similarity"] <= 1.01 for h in mean["hits"] if h["similarity"] is not None)

# 5. if embeddings fail, search still works with keywords and says so
c2 = FakeGemini(); c2.fail_embed = True
fb = idx.search("withdrawal stuck", c2, k=3)
assert fb["method"] == "keyword" and "unavailable" in fb["note"] and fb["hits"]

# 6. signal filter
assert all(h["signal"] == "reddit" for h in idx.search("money stuck", c, k=5, signal_types={"reddit"})["hits"])

# 7. claim -> top evidence table
claims = dl.load_claims("groww")["claims"]
table = idx.match_claims(claims, c, k=4)
assert set(table) == {cl["id"] for cl in claims} and all(len(v["hits"]) <= 4 for v in table.values())

# 8. analysis with retrieval: Gemini gets only the best matches, claims carry top_matches, result stores the table
FakeGemini.prompts.clear()
r = pipeline.analyze("groww", c, retrieve=True)
sent = FakeGemini.prompts[-1]
assert "top_matches" in sent and r["retrieval"] and set(r["retrieval"]) == {cl["id"] for cl in claims}
assert len(r["items"]) < len(pool)                                       # fewer items sent than the whole pool
assert {"m1", "j1"} <= {i["item_id"] for i in r["items"]}                # statistics and job counts always stay
assert len(r["findings"]) == 8 and r["gap_score"]["total_claims"] == 8
r0 = pipeline.analyze("groww", c)                                        # default behaviour is unchanged
assert r0["retrieval"] is None

# 9. questions use retrieval and return what was retrieved, with scores
a = pipeline.ask("groww", "why is my money stuck when I try to withdraw?", c)
assert a["can_answer"] and a["search_method"] == "meaning+keyword" and a["retrieved"] and "similarity" in a["retrieved"][0]
assert "bogus" not in json.dumps(a["sources"])
assert "does not give buy" in pipeline.ask("groww", "Should I buy Groww shares?", c)["answer"]

# 10. user-entered claim
ck = pipeline.check_claim("groww", "Withdrawals are processed quickly and reliably", c)
assert ck["finding"]["verdict"] in ("watch", "insufficient_evidence", "consistent", "gap") and ck["retrieved"]
assert ck["finding"]["quote"] == "Withdrawals are processed quickly and reliably"
assert "error" in pipeline.check_claim("groww", "hi", c) and "error" in pipeline.check_claim("groww", "Should I buy Groww?", c)

# 11. search with no key / no client still works (keywords)
assert pipeline.search("groww", "customer care no reply", None)["hits"]
assert pipeline.search("groww", "   ", None)["hits"] == []


# 12. general-knowledge questions: answered as labelled background; repeated questions come from the cache; advice still refused
class BgGemini(FakeGemini):
    calls = 0
    def generate_json(self, system, user, fast=False):
        if "answer from your general knowledge" in system.lower() or "You answer questions" in system:
            BgGemini.calls += 1
            return {"can_answer": True, "basis": "background", "answer": "Groww is an Indian investing platform.", "used_item_ids": ["m1"]}
        return super().generate_json(system, user, fast)

bg = BgGemini()
b1 = pipeline.ask("groww", "what does margin trading mean?", bg)
assert b1["can_answer"] and b1["basis"] == "background" and b1["sources"] == [] and b1["retrieved"] == []
assert "General background" in b1["answer"]
b2 = pipeline.ask("groww", "What does   margin TRADING mean?", bg)                      # same question, different spacing and case
assert b2.get("cached") is True and BgGemini.calls == 1
assert "does not give buy" in pipeline.ask("groww", "should I buy groww", bg)["answer"] and BgGemini.calls == 1


# 13. the overview given to the model covers every company, with counts calculated by code
ov = pipeline._overview("groww")
assert ov["verdict_counts"]["insufficient_evidence"] + ov["verdict_counts"]["watch"] + ov["verdict_counts"]["gap"] + ov["verdict_counts"]["consistent"] == 8
assert [o["slug"] for o in pipeline._all_overviews("groww")] == ["groww"]      # only companies with saved results are listed

# 14. questions about Gap itself: no background label, no sources; the chat model is tried first, the main model is the backup
class AboutGemini(FakeGemini):
    def generate_json(self, system, user, fast=False):
        if "chat assistant of 'Gap'" in system:
            assert "TinyFish" in system                                  # the facts about Gap are in the instructions
            return {"can_answer": True, "basis": "about_gap", "answer": "Gap uses Gemini.", "used_item_ids": ["m1"]}
        return super().generate_json(system, user, fast)

ab = pipeline.ask("groww", "which AI model do you use?", AboutGemini())
assert ab["basis"] == "about_gap" and ab["sources"] == [] and "General background" not in ab["answer"]

from backend import gemini_client as gc
gc.time.sleep = lambda x: None
class _T:
    class GenerateContentConfig:
        def __init__(self, **k): pass
class _R: text = '{"ok": 1}'
tried = []
class _M:
    def generate_content(self, model, contents, config):
        tried.append(model)
        if model == "chat-m": raise RuntimeError("503 UNAVAILABLE")
        return _R()
cl = gc.GeminiClient.__new__(gc.GeminiClient); cl.model = "main-m"; cl._types = _T; cl._client = type("C", (), {"models": _M()})()
config.GEMINI_CHAT_MODEL, config.GEMINI_FALLBACK_MODEL = "chat-m", ""
cl.generate_json("s", "u", fast=True)
assert tried == ["chat-m", "chat-m", "main-m"], tried                     # chat model busy -> main model answers, quickly
tried.clear(); cl.generate_json("s", "u")                                  # non-chat calls never use the chat model
assert tried == ["main-m"], tried
config.GEMINI_CHAT_MODEL = ""
print("ALL RETRIEVAL TESTS PASSED")
shutil.rmtree(tmp)
