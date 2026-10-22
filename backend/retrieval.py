"""Semantic retrieval: find the evidence that is closest in MEANING to a claim or a question.

Two searches run side by side and are merged by rank:
  1. Meaning search  - Gemini embeddings (vectors) compared with cosine similarity.
  2. Keyword search  - TF-IDF (pure Python, no packages, works offline).
Merging uses Reciprocal Rank Fusion, so the two scores never have to be on the same scale.
If the embedding service is down or no vectors are saved yet, the keyword search alone still works.

The pool searched is wider than what Gemini used to see: ALL reviews and Reddit posts, not just a capped sample,
plus the statistics, job and news evidence items. Vectors for the pool are saved once in
data/processed/<slug>/embeddings.json, so a question only needs to embed the question itself.
"""
import hashlib
import math
import re

from . import config, data_loader as dl, signals

RRF_K = 60
STOP = set("a an and are as at be but by for from has have in is it its of on or that the their this to was were will with we our they them i you your not no so if than then there these those which who what when how can could should would may might also into more most very just about over after before again".split())


# ---------------------------------------------------------------- the evidence pool
def _h(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8]


def _norm(t):
    return re.sub(r"\W+", " ", str(t or "").lower()).strip()


def build_pool(slug):
    """Every piece of evidence we could show, as items with the same shape the analysis uses.
    Rebuilt from the stored files, so it needs no Gemini call."""
    from . import pipeline                       # imported here to avoid a circular import
    nc_path = dl.processed_path(slug, "news_classified.json")
    nc = dl.read_json(nc_path) if nc_path.exists() else None
    sdata, _ = pipeline.load_all(slug, nc)
    items, _, _ = signals.build(sdata)
    pool = list(items)
    seen = {(i["signal"], _norm(i["text"])) for i in items}

    for rv in (sdata.get("reviews") or []):                       # ALL reviews, not only the capped sample
        app = (rv or {}).get("app_name") or "App"
        for r in (rv or {}).get("reviews", []):
            text = signals._cap(r.get("text", ""))
            if not text or ("reviews", _norm(text)) in seen:
                continue
            seen.add(("reviews", _norm(text)))
            pool.append({"item_id": f"v{_h(app, r.get('date'), text)}", "signal": "reviews",
                         "title": f"{app} review ({r.get('rating')} star)", "source_url": (rv or {}).get("url"),
                         "date": str(r.get("date", ""))[:10], "text": text})
    for rd in (sdata.get("reddit") or []):                        # ALL Reddit posts
        for p in (rd or {}).get("posts", []):
            text = signals._cap(f"r/{p.get('subreddit', '?')}: {p.get('title', '')} — {p.get('snippet', '')}")
            if not p.get("url") or ("reddit", _norm(text)) in seen:
                continue
            seen.add(("reddit", _norm(text)))
            pool.append({"item_id": f"x{_h(p.get('url'))}", "signal": "reddit", "title": signals._cap(p.get("title"), 120),
                         "source_url": p["url"], "date": str(p.get("date", ""))[:10], "text": text})
    return pool


def _doc_text(it):
    return f"{it.get('title', '')}. {it.get('text', '')}"


# ---------------------------------------------------------------- keyword search (TF-IDF)
def _stem(w):
    for suf in ("ingly", "edly", "ing", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _tokens(text):
    words = [_stem(w) for w in re.findall(r"[a-z0-9]+", str(text).lower()) if w not in STOP and len(w) > 1]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


class _Tfidf:
    def __init__(self, texts):
        docs = [_tokens(t) for t in texts]
        n = len(docs)
        df = {}
        for d in docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        self.idf = {w: math.log((1 + n) / (1 + c)) + 1 for w, c in df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, toks):
        tf = {}
        for w in toks:
            if w in self.idf:
                tf[w] = tf.get(w, 0) + 1
        v = {w: (1 + math.log(c)) * self.idf[w] for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def scores(self, query):
        q = self._vec(_tokens(query))
        return [sum(x * d.get(w, 0.0) for w, x in q.items()) for d in self.vecs]


# ---------------------------------------------------------------- vectors
def _unit(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def _load_vectors(slug, pool):
    p = dl.processed_path(slug, "embeddings.json")
    if not p.exists():
        return {}, {}
    cache = dl.read_json(p)
    if cache.get("model") != config.EMBED_MODEL or cache.get("dim") != config.EMBED_DIM:
        return {}, {}
    want = {i["item_id"]: _h(_doc_text(i)) for i in pool}
    vecs = {k: v["v"] for k, v in cache.get("docs", {}).items() if want.get(k) == v.get("h")}
    return vecs, cache


def build_vectors(slug, client):
    """Embed every piece of evidence that has no saved vector yet and save to embeddings.json. Run once per data refresh.
    Works in small batches with a pause (the free tier allows ~100 texts a minute) and saves after each batch,
    so if it stops you can simply run it again and it continues where it left off."""
    import time
    pool = build_pool(slug)
    vecs, _ = _load_vectors(slug, pool)
    todo = [i for i in pool if i["item_id"] not in vecs]
    total = len(todo)

    def save():
        docs = {i["item_id"]: {"h": _h(_doc_text(i)), "v": vecs[i["item_id"]]} for i in pool if i["item_id"] in vecs}
        dl.write_json(dl.processed_path(slug, "embeddings.json"), {"model": config.EMBED_MODEL, "dim": config.EMBED_DIM, "docs": docs})

    for k in range(0, total, config.EMBED_BATCH):
        if k:
            time.sleep(config.EMBED_PAUSE)
        chunk = todo[k: k + config.EMBED_BATCH]
        for it, v in zip(chunk, client.embed([_doc_text(i) for i in chunk], "RETRIEVAL_DOCUMENT")):
            vecs[it["item_id"]] = [round(x, 4) for x in _unit(v)]
        save()
        print(f"  embedded {min(k + config.EMBED_BATCH, total)} of {total}", flush=True)
    if not total:
        save()
    return {"documents": len(pool), "newly_embedded": total}


# ---------------------------------------------------------------- the index
class Index:
    def __init__(self, slug, pool, vecs):
        self.slug, self.pool, self.vecs = slug, pool, vecs
        self.tfidf = _Tfidf([_doc_text(i) for i in pool])
        # meaning search only if (almost) every document has a saved vector
        self.has_vectors = len(pool) > 0 and sum(1 for i in pool if i["item_id"] in vecs) >= 0.9 * len(pool)

    def search(self, query, client=None, k=10, signal_types=None, exclude_ids=()):
        """Best k evidence items for the query, each with similarity scores. Never raises: falls back to keywords."""
        kw = self.tfidf.scores(query)
        qvec, note = None, None
        if self.has_vectors and client is not None:
            try:
                from .gemini_client import _with_timeout
                qvec = _unit(_with_timeout(lambda: client.embed([query], "RETRIEVAL_QUERY")[0], config.EMBED_QUERY_TIMEOUT))
            except Exception as e:                    # noqa: BLE001 - any failure means: use keywords only
                note = f"meaning search unavailable ({str(e)[:80]}); used keyword search"
        elif client is not None and not self.has_vectors:
            note = "no saved vectors yet; used keyword search"
        em = [_cos(qvec, self.vecs[i["item_id"]]) if qvec and i["item_id"] in self.vecs else None for i in self.pool]

        allowed = [n for n, i in enumerate(self.pool)
                   if (not signal_types or i["signal"] in signal_types) and i["item_id"] not in exclude_ids]

        def ranks(vals):
            order = sorted((n for n in allowed if vals[n] is not None), key=lambda n: vals[n], reverse=True)
            return {n: r for r, n in enumerate(order, 1)}
        r_kw = ranks(kw)
        r_em = ranks(em) if qvec else {}
        fused = {}
        for n in allowed:
            s = 0.0
            if n in r_kw and kw[n] > 0:
                s += 1 / (RRF_K + r_kw[n])
            if n in r_em:
                s += 1 / (RRF_K + r_em[n])
            if s > 0:
                fused[n] = s
        top = sorted(fused, key=lambda n: fused[n], reverse=True)[:k]
        hits = []
        for n in top:
            it = self.pool[n]
            hits.append({**it, "similarity": round(em[n], 3) if em[n] is not None else None,
                         "keyword_score": round(kw[n], 3), "rank_score": round(fused[n] * (RRF_K + 1) / (2 if qvec else 1), 3)})
        return {"method": "meaning+keyword" if qvec else "keyword", "note": note, "hits": hits}

    def match_claims(self, claims, client=None, k=None):
        """For each claim: the top evidence by meaning. The 'claim -> evidence' table you can show."""
        k = k or config.RETRIEVAL_K
        out = {}
        for c in claims:
            q = f"{c.get('quote', '')} {c.get('what_to_look_for', '')}"
            out[c["id"]] = self.search(q, client, k)
        return out


_CACHE = {}


def get_index(slug):
    """Index for one company; rebuilt only when the data or the saved vectors change."""
    pool = build_pool(slug)
    vecs, _ = _load_vectors(slug, pool)
    sig = (_h(*sorted(i["item_id"] for i in pool)), len(vecs))
    if _CACHE.get(slug, (None,))[0] != sig:
        _CACHE[slug] = (sig, Index(slug, pool, vecs))
    return _CACHE[slug][1]
