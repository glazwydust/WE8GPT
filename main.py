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


@app.get("/companies")
def companies():
    return dl.list_companies()


@app.get("/findings/{slug}")
def findings(slug: str):
    try:
        return pipeline.load_findings(slug)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/analyze/{slug}")
def analyze(slug: str, refresh_news: bool = False):
    try:
        return pipeline.analyze(slug, client(), force_classify=refresh_news)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except (GeminiError, ValueError) as e:
        raise HTTPException(502, str(e))


@app.post("/ask/{slug}")
def ask(slug: str, body: Ask):
    try:
        return pipeline.ask(slug, body.question, client())
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except GeminiError as e:
        raise HTTPException(502, str(e))
