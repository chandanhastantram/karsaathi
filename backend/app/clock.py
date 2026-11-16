"""Demo clock. Set KARSAATHI_TODAY=YYYY-MM-DD to replay a scenario on a fixed date."""
import os
from datetime import date, datetime, time


def today() -> date:
    v = os.environ.get("KARSAATHI_TODAY")
    return date.fromisoformat(v) if v else date.today()


def now() -> datetime:
    t = today()
    real = datetime.now()
    return datetime.combine(t, real.time()) if t != real.date() else real


def period_of(d: date) -> str:
    return f"{d.month:02d}{d.year}"


def period_bounds(period: str) -> tuple[date, date]:
    m, y = int(period[:2]), int(period[2:])
    start = date(y, m, 1)
    end = date(y + (m == 12), (m % 12) + 1, 1)
    from datetime import timedelta
    return start, end - timedelta(days=1)


def prev_period(period: str) -> str:
    m, y = int(period[:2]), int(period[2:])
    return f"{12 if m == 1 else m - 1:02d}{y - 1 if m == 1 else y}"


def next_period(period: str) -> str:
    m, y = int(period[:2]), int(period[2:])
    return f"{1 if m == 12 else m + 1:02d}{y + 1 if m == 12 else y}"


def period_label(period: str) -> str:
    import calendar
    return f"{calendar.month_abbr[int(period[:2])]} {period[2:]}"


def filing_period() -> str:
    """The month whose return is due now (the previous calendar month)."""
    return prev_period(period_of(today()))


def eod(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59))
