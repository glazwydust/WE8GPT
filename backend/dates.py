"""Forgiving date reader. Returns an ISO date string (YYYY-MM-DD) or None. Never guesses silently:
relative dates ('2 days ago') need a reference date; dates with no year assume the reference year."""
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

IST = timezone(timedelta(hours=5, minutes=30))
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _mk(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def parse_any(value, ref=None):
    """ref: a date (when the data was collected). Returns 'YYYY-MM-DD' or None."""
    if value is None or value == "":
        return None
    ref = ref or datetime.now(IST).date()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        v = float(value)
        if v > 1e12:
            v /= 1000.0
        if v > 1e9:
            return datetime.fromtimestamp(v, IST).date().isoformat()
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        d = _mk(*m.groups())
        return d.isoformat() if d else None
    if re.match(r"^[A-Za-z]{3},\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{4}", s):
        try:
            return parsedate_to_datetime(s).astimezone(IST).date().isoformat()
        except (TypeError, ValueError):
            pass
    t = s.lower().replace(",", " ")
    t = re.sub(r"\s+", " ", t).strip()
    m = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", t)          # Indian style day/month/year
    if m:
        d = _mk(m.group(3), m.group(2), m.group(1))
        return d.isoformat() if d else None
    m = re.match(r"^([a-z]{3})[a-z]*\.? (\d{1,2})(?: (\d{4}))?$", t)    # Oct 12 2026 / Oct 12
    if m and m.group(1) in MONTHS:
        return _with_year(MONTHS[m.group(1)], int(m.group(2)), m.group(3), ref)
    m = re.match(r"^(\d{1,2}) ([a-z]{3})[a-z]*\.?(?: (\d{4}))?$", t)    # 12 Oct 2026 / 12 Oct
    if m and m.group(2) in MONTHS:
        return _with_year(MONTHS[m.group(2)], int(m.group(1)), m.group(3), ref)
    if t in ("today", "just now"):
        return ref.isoformat()
    if t == "yesterday":
        return (ref - timedelta(days=1)).isoformat()
    m = re.match(r"^(an?|\d+) (second|minute|min|hour|hr|day|week|month|year)s? ago$", t)
    if m:
        n = 1 if m.group(1) in ("a", "an") else int(m.group(1))
        days = {"second": 0, "minute": 0, "min": 0, "hour": 0, "hr": 0, "day": n, "week": 7 * n,
                "month": 30 * n, "year": 365 * n}[m.group(2)]
        return (ref - timedelta(days=days)).isoformat()
    return None


def _with_year(mon, day, year, ref):
    if year:
        d = _mk(year, mon, day)
    else:
        d = _mk(ref.year, mon, day)
        if d and d > ref:
            d = _mk(ref.year - 1, mon, day)
    return d.isoformat() if d else None
