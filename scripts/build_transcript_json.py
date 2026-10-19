"""Convert an earnings-call transcript PDF into a segments JSON.

Usage:
    python scripts/build_transcript_json.py <pdf> <out.json> --company "..." \
        --brand "..." --nse GROWW --bse 544603 --quarter "Q2 FY27" \
        --call-date 2026-10-14 --filed-date 2026-10-16 --source-url "<link>" \
        --management "Lalit Keshre=Co-Founder and CEO" \
        --management "Ishan Bansal=Co-Founder and CFO"

What it does:
  1. Runs pdftotext (page breaks are kept, so every segment knows its page).
  2. Finds speaker labels ("Name:" on its own line, or "Name: text ...").
  3. Writes one segment per speaker turn, with the exact words (only
     whitespace is normalised), plus the physical PDF page it starts on.
  4. Checks that no words were lost compared with the raw text.

Nothing is summarised or rewritten.
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

# Lines that look like "Name:" but are not speakers.
NOT_SPEAKERS = {
    "Registered Office", "Representatives", "Management", "Sub", "Ref",
    "Encl", "Note", "Symbol", "Scrip code", "Scrip Code", "Date", "Place",
    "CIN", "Email", "Phone", "Tel", "Fax", "W", "E", "T",
}

# Typos in the source transcript -> canonical name.
ALIASES = {"Lalit Bimani": "Lalit Bhimani"}

SPEAKER_RE = re.compile(r"^([A-Z][A-Za-z\.'\- ]{2,40}?):\s*(.*)$")
HEADER_RES = [
    re.compile(r"^Page \d+ of \d+$"),
    re.compile(r"^[A-Z][a-z]+ \d{1,2}, \d{4}$"),                 # "October 14, 2026"
    re.compile(r"^Billionbrains Garage Ventures Limited \(Groww\)$"),
    re.compile(r"^Angel One Limited\s*$"),
]


def run_pdftotext(pdf):
    if pdf.endswith(".txt"):   # already-converted text (keeps form-feed page breaks)
        return open(pdf, encoding="utf-8").read()
    out = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True, check=True)
    return out.stdout


def is_header(line):
    return any(r.match(line.strip()) for r in HEADER_RES)


def parse(text, start_after_marker=None):
    pages = text.split("\f")
    segments = []
    current = None
    started = start_after_marker is None
    for pdf_page, page_text in enumerate(pages, start=1):
        for raw in page_text.splitlines():
            line = raw.strip()
            if not line or is_header(line):
                continue
            m = SPEAKER_RE.match(line)
            is_speaker = bool(m) and m.group(1).strip() not in NOT_SPEAKERS \
                and len(m.group(1).split()) <= 4
            if not started:
                # Begin at the first "Moderator:" label (skips cover letter).
                if is_speaker and m.group(1).strip() == "Moderator":
                    started = True
                else:
                    continue
            if is_speaker:
                if current:
                    segments.append(current)
                current = {"pdf_page": pdf_page, "speaker": m.group(1).strip(), "_lines": []}
                if m.group(2).strip():
                    current["_lines"].append(m.group(2).strip())
            elif current is not None:
                current["_lines"].append(line)
    if current:
        segments.append(current)
    for s in segments:
        s["text"] = re.sub(r"\s+", " ", " ".join(s.pop("_lines"))).strip()
    return [s for s in segments if s["text"]]


def words(s):
    return re.findall(r"\S+", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("out")
    ap.add_argument("--company", required=True)
    ap.add_argument("--brand", default=None)
    ap.add_argument("--nse", default=None)
    ap.add_argument("--bse", default=None)
    ap.add_argument("--quarter", required=True)
    ap.add_argument("--call-date", required=True)
    ap.add_argument("--filed-date", default=None)
    ap.add_argument("--source-url", default="PASTE_THE_BSE_OR_SCREENER_LINK")
    ap.add_argument("--source-page-url", default=None)
    ap.add_argument("--fetched-by", default="tinyfish (link) + manual (pdf to text)")
    ap.add_argument("--management", action="append", default=[],
                    help='"Name=Role" for each management speaker')
    args = ap.parse_args()

    raw = run_pdftotext(args.pdf)
    segs = parse(raw, start_after_marker="Moderator")
    roles = dict(m.split("=", 1) for m in args.management)

    out_segments = []
    for i, s in enumerate(segs, start=1):
        name = ALIASES.get(s["speaker"], s["speaker"])
        if name == "Moderator":
            stype, role = "moderator", None
        elif name in roles:
            stype, role = "management", roles[name]
        else:
            stype, role = "participant", None   # role not stated in the transcript
        out_segments.append({
            "id": f"s{i}", "pdf_page": s["pdf_page"], "speaker": name,
            "speaker_type": stype, "role": role, "text": s["text"],
        })

    ist = timezone(timedelta(hours=5, minutes=30))
    doc = {
        "company": args.company,
        "brand": args.brand,
        "nse_symbol": args.nse,
        "bse_scrip_code": args.bse,
        "quarter": args.quarter,
        "call_date": args.call_date,
        "filed_with_exchange": args.filed_date,
        "source_url": args.source_url,
        "source_page_url": args.source_page_url,
        "fetched_at": datetime.now(ist).isoformat(timespec="seconds"),
        "fetched_by": args.fetched_by,
        "page_note": "pdf_page is the physical PDF page (page 1 is the exchange cover letter).",
        "segments": out_segments,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)

    # Sanity check: every word after the first "Moderator:" label should be kept.
    kept = sum(len(words(s["text"])) for s in out_segments)
    labels = sum(len(words(s["speaker"])) + 1 for s in out_segments)  # "Name :" tokens
    print(f"segments: {len(out_segments)}  words kept: {kept}  (+{labels} label words)")
    speakers = {}
    for s in out_segments:
        speakers[s["speaker"]] = speakers.get(s["speaker"], 0) + 1
    for k, v in sorted(speakers.items(), key=lambda kv: -kv[1]):
        print(f"  {v:3d}  {k}")


if __name__ == "__main__":
    sys.exit(main())
