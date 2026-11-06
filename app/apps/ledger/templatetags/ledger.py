import json
from decimal import ROUND_HALF_UP, Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe


register = template.Library()

# Burrow's stroke icons (24 grid, 2.2 stroke, round caps), plus a few drawn to match.
ICONS = {
    "home": "M4 11 L12 4 L20 11 V20 H14 V14 H10 V20 H4 Z",
    "plus": "M12 5 V19 M5 12 H19",
    "chart": "M5 19 V11 M12 19 V5 M19 19 V14",
    "gear": "M12 9 A3 3 0 1 0 12 15 A3 3 0 1 0 12 9 Z M12 3 V5.5 M12 18.5 V21 M3 12 H5.5 M18.5 12 H21 M5.6 5.6 L7.4 7.4 M16.6 16.6 L18.4 18.4 M5.6 18.4 L7.4 16.6 M16.6 7.4 L18.4 5.6",
    "wallet": "M4 7 H18 A2 2 0 0 1 20 9 V18 A2 2 0 0 1 18 20 H6 A2 2 0 0 1 4 18 Z M4 7 L15 4 V7 M15.5 13.5 H16.5",
    "search": "M10.5 4 A6.5 6.5 0 1 0 10.5 17 A6.5 6.5 0 1 0 10.5 4 Z M15.5 15.5 L20 20",
    "arrow-up": "M12 19 V5 M6 11 L12 5 L18 11",
    "arrow-down": "M12 5 V19 M6 13 L12 19 L18 13",
    "check": "M5 12.5 L10 17.5 L19 7",
    "calendar": "M5 6 H19 V20 H5 Z M5 10 H19 M9 3.5 V7.5 M15 3.5 V7.5",
    "x": "M6 6 L18 18 M18 6 L6 18",
    "chevron-left": "M15 5 L8 12 L15 19",
    "chevron-right": "M9 5 L16 12 L9 19",
    "chevron-down": "M5 9 L12 16 L19 9",
    "trash": "M4 7 H20 M9 7 V4.5 H15 V7 M6.5 7 L7.5 20 H16.5 L17.5 7 M10 11 V16 M14 11 V16",
    "repeat": "M4 12 V10 A4 4 0 0 1 8 6 H18 M15 3 L18 6 L15 9 M20 12 V14 A4 4 0 0 1 16 18 H6 M9 21 L6 18 L9 15",
    "note": "M6 4 H14 L19 9 V20 H6 Z M14 4 V9 H19 M9 13 H15 M9 16.5 H13",
    "pencil": "M5 19 L6 14.5 L15.5 5 A2 2 0 0 1 19 8.5 L9.5 18 Z M13.5 7 L17 10.5",
    "list": "M9 6 H20 M9 12 H20 M9 18 H20 M4.5 6 H5 M4.5 12 H5 M4.5 18 H5",
    "logout": "M14 4 H6 V20 H14 M10 12 H21 M17 8 L21 12 L17 16",
    "pause": "M8 5 V19 M16 5 V19",
    "play": "M7 4.5 V19.5 L19 12 Z",
    "sun": "M12 8 A4 4 0 1 0 12 16 A4 4 0 1 0 12 8 Z M12 2.5 V4.5 M12 19.5 V21.5 M2.5 12 H4.5 M19.5 12 H21.5 M5.3 5.3 L6.7 6.7 M17.3 17.3 L18.7 18.7 M5.3 18.7 L6.7 17.3 M17.3 6.7 L18.7 5.3",
    "moon": "M19 14.5 A7.5 7.5 0 1 1 9.5 5 A6 6 0 0 0 19 14.5 Z",
    "key": "M8 10 A4 4 0 1 0 8 18 A4 4 0 1 0 8 10 Z M11 11 L20 4 M17 6.5 L19.5 9 M15 8 L17 10",
}


@register.simple_tag
def icon(name, size=24, label=""):
    d = ICONS.get(name, ICONS["plus"])
    aria = format_html('role="img" aria-label="{}"', label) if label else mark_safe('aria-hidden="true"')
    return format_html(
        '<svg class="bh-icon" width="{s}" height="{s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" {aria}><path d="{d}"/></svg>',
        s=size,
        aria=aria,
        d=d,
    )


def format_money(value, signed=False, type=None):
    """``$1,234.50``. ``signed`` adds ``−`` for an expense and ``+`` for income
    (``type`` says which; without it a negative value counts as income)."""
    if value is None or value == "":
        return ""
    value = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = f"${abs(value):,.2f}"
    if signed:
        income = type == "income" if type else value < 0
        return f"+{text}" if income else f"\u2212{text}"
    return f"\u2212{text}" if value < 0 else text


@register.simple_tag
def money(value, signed=False, type=None):
    return format_money(value, signed, type)


@register.inclusion_tag("ledger/partials/entry.html", takes_context=True)
def entry_flow(context):
    """The add/edit flow, with categories ordered by recent use and past titles."""
    from django.utils import timezone

    from apps.ledger.services import categories_for_entry, title_suggestions

    request = context.get("request")
    if not (request and request.user.is_authenticated):
        return {"cats": [], "entry_data": None}
    cats = categories_for_entry()
    return {
        "request": request,
        "cats": cats,
        "entry_data": {
            "cats": [{"id": c.id, "name": c.name, "kind": c.kind} for c in cats],
            "titles": title_suggestions(),
            "today": timezone.localdate().isoformat(),
        },
    }


@register.filter
def spend_json(t):
    """JSON for a row's data-spend attribute (opens the edit sheet)."""
    return json.dumps(t.as_entry())


@register.filter
def neg(value):
    return -value


@register.filter
def sub(value, other):
    return value - other


@register.filter
def pct_clamp(value, top=100):
    """Clamp a percentage into 0..top for widths."""
    try:
        return max(0, min(int(top), int(value or 0)))
    except (TypeError, ValueError):
        return 0
