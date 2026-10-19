"""Command line:   python -m backend.cli analyze groww
                   python -m backend.cli ask groww "Is the pricing claim backed up?"
                   python -m backend.cli check groww      (reads the data files, shows problems, NO Gemini call)
"""
import json
import sys
from . import data_loader as dl, pipeline
from .gemini_client import GeminiClient


def main(argv):
    if len(argv) < 3 or argv[1] not in ("analyze", "ask", "check"):
        print(__doc__)
        return 1
    if argv[1] == "check":
        slug = argv[2]
        try:
            dl.load_claims(slug)
            print(f"claims: OK ({len(dl.load_claims(slug)['claims'])} claims)")
        except FileNotFoundError as e:
            print(f"claims: MISSING - {e}")
        nc = None
        p = dl.processed_path(slug, "news_classified.json")
        if p.exists():
            nc = dl.read_json(p)
        data, quality = pipeline.load_all(slug, nc)
        if nc is None:                       # not classified yet: still report the raw news file
            raw, fname = dl.load_signal(slug, "news")
            quality = [q for q in quality if q["signal"] != "news"]
            quality.append({"signal": "news", "file": fname, "count": len((raw or {}).get("articles", [])),
                            "collected_at": (raw or {}).get("collected_at"),
                            "warnings": [] if raw else ["no file found for this signal"]})
            if raw:
                quality[-1]["warnings"].append("not classified yet (Gemini does that on the first 'analyze')")
        for q in quality:
            print(f"{q['signal']:<8} {str(q['file']):<42} count={q['count']}  collected_at={q['collected_at']}")
            for w in q["warnings"]:
                print(f"           ! {w}")
        items, summary, _ = pipeline.signals.build(data)
        print(f"\nevidence items the model would see: {len(items)}")
        for f in summary.get("flags", []):
            print("flag:", f)
        return 0
    c = GeminiClient()
    if argv[1] == "analyze":
        r = pipeline.analyze(argv[2], c)
        for f in r["findings"]:
            print(f"[{f['verdict']:<21}] #{f['claim_id']} {f['topic']}  ({', '.join(f['signal_types']) or 'no evidence'})")
        print(f"\nsaved -> data/processed/{argv[2]}/findings.json" + ("  (STALE: " + r["error"] + ")" if r.get("stale") else ""))
    else:
        print(json.dumps(pipeline.ask(argv[2], " ".join(argv[3:]), c), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
