"""HTTP API for the dashboard.  Run from the repo root:  uvicorn backend.main:app --reload
The browser only ever talks to this server. Keys stay in environment variables here."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import data_loader as dl, pipeline
from .gemini_client import GeminiClient, GeminiError

app = FastAPI(title="Gap API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # tighten for production

_client = None


def client():
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client


class Ask(BaseModel):
    question: str


class Check(BaseModel):
    claim: str


@app.get("/companies")
def companies():
    return dl.list_companies()


@app.get("/findings/{slug}")
def findings(slug: str):
    slug = slug.lower().strip()
    try:
        return pipeline.load_findings(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/score/{slug}")
def gap_score(slug: str):
    slug = slug.lower().strip()
    try:
        return pipeline.load_findings(slug)["gap_score"]
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/search/{slug}")
def search(slug: str, q: str, k: int = 10, signal: str = ""):
    """Semantic search over the evidence. Instant, no Gemini text call. signal = reviews, jobs, reddit or news (optional)."""
    slug = slug.lower().strip()
    try:
        try:
            c = client()
        except GeminiError:
            c = None                                  # no key: keyword search still works
        return pipeline.search(slug, q, c, k=k, signal_types={signal} if signal else None)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/match/{slug}")
def match(slug: str, k: int = 10):
    """Each claim with the evidence closest in meaning, and the similarity scores."""
    slug = slug.lower().strip()
    try:
        claims = dl.load_claims(slug)["claims"]
        try:
            c = client()
        except GeminiError:
            c = None
        m = pipeline.retrieval.get_index(slug).match_claims(claims, c, k=max(1, min(k, 20)))
        return [{"claim_id": cl["id"], "topic": cl["topic"], "quote": cl["quote"], "method": m[cl["id"]]["method"],
                 "evidence": [{**pipeline._public(h), "text": h["text"]} for h in m[cl["id"]]["hits"]]} for cl in claims]
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/check/{slug}")
def check(slug: str, body: Check):
    """The user types a statement; Gap finds the closest evidence and gives a verdict (not saved)."""
    slug = slug.lower().strip()
    try:
        return pipeline.check_claim(slug, body.claim, client())
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except GeminiError as e:
        raise HTTPException(502, str(e))


@app.post("/analyze/{slug}")
def analyze(slug: str, refresh_news: bool = False, retrieve: bool = False):
    slug = slug.lower().strip()
    try:
        return pipeline.analyze(slug, client(), force_classify=refresh_news, retrieve=retrieve)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except (GeminiError, ValueError) as e:
        raise HTTPException(502, str(e))


@app.post("/ask/{slug}")
def ask(slug: str, body: Ask):
    slug = slug.lower().strip()
    try:
        return pipeline.ask(slug, body.question, client())
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except GeminiError as e:
        raise HTTPException(502, str(e))
