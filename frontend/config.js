// The only file you may need to edit.
//
// API_BASE is the FastAPI backend (uvicorn backend.main:app). It is OPTIONAL:
// the site shows everything from data/bundle.js without it. With the backend
// running, the Ask Gap page gets AI answers instead of the offline search.
//   local:    "http://localhost:8000"
//   hosted:   "https://your-backend.onrender.com"   (must be https if the site is https)
//   none:     ""
window.GAP_CONFIG = {
  API_BASE: "http://localhost:8000",
  API_PROBE_MS: 1200,
};
