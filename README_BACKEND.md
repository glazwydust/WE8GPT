# Gap backend (Groww)

Flow: stored JSON -> Python counts the numbers -> Gemini labels news and judges each claim -> Python validates -> `findings.json` -> dashboard.
The browser never sees API keys. TinyFish is used to collect the signal files (reviews, jobs, Reddit, news) and to find the transcript link; the transcript PDF was converted to text locally (`scripts/build_transcript_json.py`).

## Folders
- `data/transcripts/` full transcript as speaker segments
- `data/claims/claims_groww.json` 8 management claims (quotes checked word for word against the transcript)
- `data/signals/groww/<signal>_<YYYY-MM-DD>.json` from Person A: `reviews_`, `jobs_`, `reddit_`, `news_`
- `data/processed/groww/` written by the backend (`news_classified.json`, `findings.json`)

## Run
```
pip install -r requirements.txt
cp .env.example .env        # then put your GEMINI_API_KEY in .env
python -m tests.test_offline                    # no key needed
python -m backend.cli analyze groww
python -m backend.cli ask groww "Is the pricing claim backed up?"
uvicorn backend.main:app --reload               # API for the dashboard
```
API: `GET /companies`, `GET /findings/{slug}`, `POST /analyze/{slug}`, `POST /ask/{slug}` with `{"question": "..."}`.

## Collecting news (TinyFish)
1. Save each TinyFish result unedited in `data/raw/tinyfish_news/` (`run1.json`, ... or `rss5.xml`, ...).
2. For Google News RSS pages: `python scripts/rss_to_run.py rss5.xml data/raw/tinyfish_news/run5.json --query "..." --query-type sector_regulatory`
3. Merge: `python scripts/merge_news.py data/raw/tinyfish_news/run*.json --out data/signals/groww/news_YYYY-MM-DD.json --company "Billionbrains Garage Ventures (Groww)" --credits <n>`
4. `python -m backend.cli analyze groww`
Note in your main README which queries TinyFish ran and which were done by hand.

## Two companies: Groww and Eternal
- Claims: `data/claims/claims_groww.json`, `data/claims/claims_eternal.json` (8 each, quotes checked word for word against the transcripts in `data/transcripts/`).
- Person A's files stay flat in `data/` with their own names: `<company>_playstore.json`, `<company>_careers.json`, `<company>_reddit.json`.
  A company with two apps (Eternal: Blinkit and Zomato) can have `eternal_blinkit_playstore.json` and `eternal_zomato_playstore.json`; each app is analysed separately.
- News: `data/signals/<company>/news_<date>.json` (built by `scripts/merge_news.py`) or a flat `data/<company>_news.json`.
- Check the data before spending Gemini calls: `python -m backend.cli check groww` / `check eternal`.
- Run: `python -m backend.cli analyze groww` / `analyze eternal`.  API: `/companies`, `/analyze/{slug}`, `/findings/{slug}`, `/ask/{slug}`.
