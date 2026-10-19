"""Reads stored JSON only. No network calls here."""
import json
import re
from pathlib import Path
from . import config


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def list_companies():
    out = []
    for p in sorted(config.CLAIMS_DIR.glob("claims_*.json")):
        d = read_json(p)
        out.append({"slug": d.get("slug") or p.stem.replace("claims_", ""),
                    "company": d.get("company"), "quarter": d.get("quarter")})
    return out


def load_claims(slug):
    p = config.CLAIMS_DIR / f"claims_{slug}.json"
    if not p.exists():
        raise FileNotFoundError(f"No claims file for '{slug}' ({p})")
    return read_json(p)


# Person A's files sit flat in data/ : <slug>_playstore.json, <slug>_careers.json, <slug>_reddit.json
# (a company with several apps has e.g. eternal_blinkit_playstore.json and eternal_zomato_playstore.json).
FLAT_KIND = {"reviews": "playstore", "jobs": "careers", "reddit": "reddit", "news": "news"}


def signal_paths(slug, signal):
    """All files for one signal. Flat names (A's) win; otherwise the newest dated file in data/signals/<slug>/."""
    kind = FLAT_KIND[signal]
    flat = sorted(p for p in config.DATA.glob(f"{slug}*_{kind}*.json") if p.is_file())
    if flat:
        return flat
    return signal_files(slug, signal)[:2]


def signal_files(slug, signal):
    """Files for one signal, newest first. Name pattern: <signal>_<YYYY-MM-DD>*.json"""
    d = config.SIGNALS_DIR / slug
    files = [p for p in d.glob(f"{signal}_*.json")
             if re.match(rf"^{signal}_\d{{4}}-\d{{2}}-\d{{2}}", p.name)]
    return sorted(files, key=lambda p: p.name, reverse=True)


def load_signal(slug, signal, which=0):
    """One raw file (used for news). Returns (data, filename) or (None, None)."""
    files = signal_paths(slug, signal)
    if len(files) <= which:
        return None, None
    return read_json(files[which]), files[which].name


def is_flat(slug, signal):
    return any(p.parent == config.DATA for p in signal_paths(slug, signal))


def load_signal_docs(slug, signal, normalizer):
    """Every file of a signal, normalised. Returns [(doc, filename, warnings)]."""
    paths = signal_paths(slug, signal)
    if not is_flat(slug, signal):
        paths = paths[:1]          # dated-folder style: newest file only (a second one is the 'previous snapshot')
    out = []
    for p in paths:
        try:
            raw = read_json(p)
        except ValueError as e:
            out.append(({}, p.name, [f"file is not valid JSON: {e}"]))
            continue
        doc, w = normalizer(raw, p, slug)
        out.append((doc, p.name, w))
    return out


def processed_path(slug, name):
    return config.PROCESSED_DIR / slug / name
