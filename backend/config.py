"""Settings. Secrets come from environment variables only (never commit them)."""
import os
from pathlib import Path

try:  # optional: load a local .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CLAIMS_DIR = DATA / "claims"
SIGNALS_DIR = DATA / "signals"        # data/signals/<slug>/<signal>_<YYYY-MM-DD>.json
PROCESSED_DIR = DATA / "processed"    # data/processed/<slug>/news_classified.json, findings.json

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Check Google's current model list and set this in .env if the default is retired.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Optional backup model, tried when the main one is overloaded (503) or out of quota. Leave empty to disable.
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "")
# Optional separate model for the chat box. It has its own daily quota, so chat never uses up the analysis quota (and the reverse).
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "")

SIGNAL_TYPES = ["reviews", "jobs", "reddit", "news"]

# Thresholds for the Python-side flags (visible rules, easy to explain to judges).
REVIEW_WINDOW_DAYS = 14
MIN_REVIEWS_PER_WINDOW = 15          # below this we refuse to compare windows
ONE_STAR_RISE_PP = 8                 # percentage points
AVG_RATING_DROP = 0.3
SERVICE_COMPLAINT_RISE_PP = 8
JOBS_DROP_PCT = 15
NEWS_NEGATIVE_FACTS = 2

MAX_REVIEW_SAMPLES = 20
MAX_REDDIT_POSTS = 15
MAX_NEWS_ARTICLES = 60
NEWS_MAX_AGE_DAYS = 365              # older articles are ignored; age is shown for the rest
NEWS_BATCH = 25
TEXT_CAP = 300                       # characters kept per review / post / snippet

# Retrieval (semantic search over the evidence)
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = 256                      # smaller vectors: small files, fast search
RETRIEVAL_K = 10                     # evidence pieces kept per claim
ASK_K = 8                            # evidence pieces sent to Gemini for a user question

# Optional: set GEMINI_THINKING_BUDGET=0 in the environment to make chat answers faster (only if your model supports it).
_tb = os.getenv("GEMINI_THINKING_BUDGET", "0")          # 0 = no extra "thinking" time for chat answers: much faster. Set to "" to turn off.
GEMINI_THINKING_BUDGET = int(_tb) if _tb.lstrip("-").isdigit() else None
# Chat time limits (seconds). If Gemini has not answered inside CHAT_DEADLINE the chat answers from the saved results instead.
CHAT_DEADLINE = float(os.getenv("CHAT_DEADLINE", "18"))
CHAT_ATTEMPT_TIMEOUT = float(os.getenv("CHAT_ATTEMPT_TIMEOUT", "12"))
CHAT_EVIDENCE_K = 8                  # evidence pieces sent with a chat question (smaller prompt = faster answer)
EMBED_QUERY_TIMEOUT = 4              # seconds: if the question cannot be embedded this fast, keyword search is used
EMBED_BATCH = 40                    # texts per embedding call. The free tier allows about 100 texts a minute
EMBED_PAUSE = 30                     # seconds to wait between batches
