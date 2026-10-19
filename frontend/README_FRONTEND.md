# Gap website

Five pages: Home, Results (per company), Claims, How it works, Ask Gap.
Plain HTML, CSS and JavaScript. **No npm, no build, no server needed.**

## See it in your browser

Double-click `frontend/index.html`. That's it. (It also works with `python -m http.server` inside `frontend/`.)

The badge at top right says **saved results**. If you also run the backend (`uvicorn backend.main:app --reload`), it turns
**live answers** and the Ask Gap page uses Gemini instead of searching the saved results.

## Where the data comes from

Everything on the site is read from `frontend/data/bundle.js`, which is generated from the repo's own files:

```bash
python scripts/build_frontend_data.py
```

It reads `data/claims/`, `data/processed/<slug>/findings.json`, the `data/<slug>_*.json` signal files and
`data/raw/tinyfish_news/`. Re-run it every time you re-run `python -m backend.cli analyze <slug>`, then commit the new `bundle.js`.

## Add another company

Nothing in the website is hard-coded to Groww or Eternal. Add `data/claims/claims_<slug>.json` and the signal files,
run `python -m backend.cli analyze <slug>` and `python scripts/build_frontend_data.py`. The new company appears on
Home, Results, Claims and Ask Gap automatically.

## Push to GitHub

**You do not need to deploy first.** Pushing and deploying are separate. Pushing only puts the files on GitHub.

```bash
git clone https://github.com/glazwydust/WE8GPT.git      # skip if you already have it
cd WE8GPT
git checkout -b frontend
# copy these from the zip into the repo root:
#   frontend/   scripts/build_frontend_data.py   .github/workflows/pages.yml
git add frontend scripts/build_frontend_data.py .github
git commit -m "Add website frontend"
git push -u origin frontend
```

Open the link GitHub prints, click **Create pull request**, then **Merge**. If a teammate pushed first, run `git pull` before pushing.
Do not commit `.env` (your Gemini key); it is already in `.gitignore`.

## What others can see once it is in the repo

- **Everything, as code:** anyone who opens the repo on GitHub can read the website source, the data script and the backend.
- **The running site, without deploying:** anyone can download or clone the repo and double-click `frontend/index.html`.
- **A link people can click:** only if you deploy (below). Put that link in the repo's About box and README.

## Deploy (optional, free)

**GitHub Pages, no other service.** The included workflow `.github/workflows/pages.yml` publishes the `frontend/` folder.
1. Merge to `main`.
2. Repo → Settings → Pages → Source: **GitHub Actions**.
3. After the next push to `main` (or Actions → "Deploy website" → Run workflow), the site is at
   `https://glazwydust.github.io/WE8GPT/`.

**Netlify or Vercel:** import the repo, set the base directory to `frontend`, leave the build command empty.

The deployed site shows everything from saved results. For live AI answers online you also need to host the backend
(Render, Railway or Fly.io, with `GEMINI_API_KEY` set) and put its https address in `frontend/config.js` as `API_BASE`.
Before that, change `allow_origins=["*"]` in `backend/main.py` to your site's address.

### Optional: serve the website from the backend

Add to the end of `backend/main.py`, then open http://localhost:8000/app/

```python
from fastapi.staticfiles import StaticFiles
app.mount("/app", StaticFiles(directory="frontend", html=True), name="frontend")
```

## Things to fix in the data

- `claims_*.json` has `source_url: "PASTE_BSE_TRANSCRIPT_LINK"`. Put the real transcript link there. Until then, the source shows as plain text.
- Eternal's careers file reports 481 roles, counted from Naukri search results rather than the official careers page, while the analysis used the 15 listings it could read. The site shows both and says so. Judges may ask, so either collect the official careers count or mention the limit.
- The "An example of a gap" box on How it works is a fictional illustration and is labelled as one.
