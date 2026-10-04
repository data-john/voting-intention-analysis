"""
Configuration: party metadata, display ordering, and the logic that maps a
worksheet name (e.g. "18-24", "Scotland", "I voted to Leave") onto a
(breakdown_category, group) pair such as ("Age", "18-24").

If a future poll export uses a sheet name this file doesn't recognise, the
loader will still keep the data (tagged category="Other/Unclassified") and
print a warning telling you to extend `classify_sheet` below -- nothing
silently gets dropped.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Parties
# ---------------------------------------------------------------------------

# Row labels as they appear in the workbook, in a sensible display order.
PARTY_ORDER = ["Con", "Lab", "Lib Dem", "Reform UK", "Green", "SNP", "Plaid Cymru", "Other"]

# The regional reporting scope for parties that contest only one UK nation.
HOME_REGION_BY_PARTY = {"SNP": "Scotland", "Plaid Cymru": "Wales"}

# Parties usually worth putting on the same "headline" charts (small multiples
# get unreadable with all 8). Plaid Cymru is added to regional charts for Wales.
# Other remains available in summary tables, but is left off default plots.
MAIN_PARTIES = ["Con", "Lab", "Lib Dem", "Reform UK", "Green", "SNP"]

PARTY_LABELS = {
    "Con": "Conservative",
    "Lab": "Labour",
    "Lib Dem": "Liberal Democrat",
    "Reform UK": "Reform UK",
    "Green": "Green",
    "SNP": "SNP",
    "Plaid Cymru": "Plaid Cymru",
    "Other": "Other",
}

# Standard UK party brand colours (used consistently across every chart).
PARTY_COLORS = {
    "Con": "#0087DC",
    "Lab": "#E4003B",
    "Lib Dem": "#FAA61A",
    "Reform UK": "#12B6CF",
    "Green": "#6AB023",
    "SNP": "#EAC435",
    "Plaid Cymru": "#005B54",
    "Other": "#8C8C8C",
}

# ---------------------------------------------------------------------------
# Sheet -> (category, group) classification
# ---------------------------------------------------------------------------

_AGE_RE = re.compile(r"^\d{2}-\d{2}$|^\d{2}\+$")

_GENDERS = {"male", "female"}

_REGIONS = {
    "london",
    "rest of south",
    "rest of the south",
    "south",
    "midlands",
    "midlands & wales",
    "north",
    "scotland",
    "wales",
}

_SOCIAL_GRADES = {"abc1", "c2de"}

# Party names as they might appear as *sheet names* when the breakdown is
# "how did you vote at the last election" (recalled vote). Kept generic
# (not tied to a specific election year) since different files may cover
# different elections (e.g. 2019 recall vs 2024 recall).
_RECALLED_VOTE_PARTIES = {
    "conservative",
    "labour",
    "liberal democrat",
    "lib dem",
    "reform uk",
    "brexit party",
    "ukip",
    "green",
    "snp",
    "scottish national party",
    "plaid cymru",
    "change uk",
    "did not vote",
    "don't know",
    "too young to vote",
}

# Preferred display order for groups within a category. Anything not listed
# is appended afterwards, alphabetically.
GROUP_ORDER = {
    "Overall": ["All adults"],
    "Age": ["18-24", "25-49", "50-64", "65+"],
    "Gender": ["Male", "Female"],
    "Region": ["London", "Rest of South", "Midlands", "North", "Scotland", "Wales"],
    "EU Ref Vote": ["Remain", "Leave"],
    "Social Grade": ["ABC1", "C2DE"],
    "Past Vote": [
        "Conservative",
        "Labour",
        "Liberal Democrat",
        "Reform UK",
        "Green",
        "SNP",
        "Plaid Cymru",
    ],
}


# Presentation only: keep workbook labels and CSV identifiers unchanged.
CATEGORY_EMOJIS = {
    "Age": "🎂", "Gender": "👥", "Region": "🗺️",
    "Social Grade": "💼", "EU Ref Vote": "🇪🇺", "Past Vote": "🗳️",
}
GROUP_EMOJIS = {
    "Age": {"18-24": "🧑", "25-49": "🧑‍💼", "50-64": "🧑‍🦳", "65+": "🧓"},
    "Gender": {"Male": "👨", "Female": "👩"},
    "Region": {
        "London": "🏙️", "Rest of South": "🌊", "Rest of the South": "🌊",
        "South": "🌊", "Midlands": "🏭", "Midlands & Wales": "🏭",
        "North": "⛰️", "Scotland": "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
        "Wales": "🏴\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f",
    },
    "Social Grade": {"ABC1": "💼", "C2DE": "🛠️"},
    "EU Ref Vote": {"Remain": "🇪🇺", "Leave": "🚪"},
    "Past Vote": {
        "Conservative": "🌳", "Labour": "🌹", "Liberal Democrat": "🕊️",
        "Lib Dem": "🕊️", "Reform UK": "➡️", "Brexit Party": "➡️",
        "UKIP": "💷", "Green": "🌿", "SNP": "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
        "Scottish National Party": "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f",
        "Plaid Cymru": "🌼", "Change UK": "🔄", "Did not vote": "🚫",
        "Don't know": "❓", "Too young to vote": "🧒",
    },
}


def category_label(category: str, title: str | None = None) -> str:
    emoji = CATEGORY_EMOJIS.get(category, "")
    return f"{title or category} {emoji}".rstrip()


def group_label(category: str, group: str) -> str:
    emojis = GROUP_EMOJIS.get(category, {})
    emoji = next((value for name, value in emojis.items() if name.casefold() == group.casefold()),
                 CATEGORY_EMOJIS.get(category, ""))
    return f"{group} {emoji}".rstrip()


def breakdown_label(label: str) -> str:
    category, separator, group = label.partition(": ")
    if not separator:
        return label
    return f"{category_label(category)}: {group_label(category, group)}"


def classify_sheet(sheet_name: str) -> tuple[str, str]:
    """Map a worksheet name to (breakdown_category, group_label).

    Examples
    --------
    >>> classify_sheet("18-24")
    ('Age', '18-24')
    >>> classify_sheet("I voted to Leave")
    ('EU Ref Vote', 'Leave')
    >>> classify_sheet("Labour")
    ('Past Vote', 'Labour')
    """
    name = sheet_name.strip()
    low = name.lower()

    if low == "all adults":
        return "Overall", "All adults"

    if _AGE_RE.match(name):
        return "Age", name

    if low in _GENDERS:
        return "Gender", name.title()

    if low in _REGIONS:
        return "Region", name

    if low in _SOCIAL_GRADES:
        return "Social Grade", name.upper()

    if "remain" in low or "leave" in low:
        group = "Remain" if "remain" in low else "Leave"
        return "EU Ref Vote", group

    if low in _RECALLED_VOTE_PARTIES:
        return "Past Vote", name

    return "Other/Unclassified", name


def order_groups(category: str, groups) -> list[str]:
    """Return `groups` sorted into a sensible display order for `category`."""
    preferred = GROUP_ORDER.get(category, [])
    ordered = [g for g in preferred if g in groups]
    remainder = sorted(g for g in groups if g not in ordered)
    return ordered + remainder
