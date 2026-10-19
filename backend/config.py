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
