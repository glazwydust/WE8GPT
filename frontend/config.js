// The only file you may need to edit.
//
// API_BASE is the FastAPI backend (uvicorn backend.main:app). It is OPTIONAL:
// the site shows everything from data/bundle.js without it. With the backend
// running, the Ask Gap page gets AI answers instead of the offline search.
//   local:    "http://localhost:8000"   (use this only while testing on your own computer)
//   hosted:   "https://your-backend.onrender.com"   (must be https if the site is https)
//   none:     ""
window.GAP_CONFIG = {
  API_BASE: "https://backend-gap.onrender.com",
  API_PROBE_MS: 60000,     // the page pings the backend on load to wake it up (a free server sleeps)
  ASK_TIMEOUT_MS: 45000,   // how long the Ask box waits for the backend before it uses the saved results
};
