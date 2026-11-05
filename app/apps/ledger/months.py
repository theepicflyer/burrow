"""Month helpers. A month is always a ``date`` with ``day=1``."""

from datetime import date

from dateutil.relativedelta import relativedelta


def month_of(d: date) -> date:
    return d.replace(day=1)


def add_months(m: date, n: int) -> date:
    return month_of(m) + relativedelta(months=n)


def month_range(first: date, last: date) -> list[date]:
    """Every month from ``first`` to ``last`` inclusive."""
    out, m, last = [], month_of(first), month_of(last)
    while m <= last:
        out.append(m)
        m = add_months(m, 1)
    return out


def parse_month(value: str | None, default: date) -> date:
    """``YYYY-MM`` (or ``YYYY-MM-DD``) to a month; ``default`` when missing or invalid."""
    if value:
        try:
            parts = [int(p) for p in value.split("-")[:2]]
            return date(parts[0], parts[1], 1)
        except (ValueError, IndexError):
            pass
    return month_of(default)
