"""
Analysis functions that turn the tidy long-format DataFrame produced by
`loader.load_all()` into summary tables: latest support, change over one or
more trailing windows, and -- the headline question -- which group each
party is currently strongest with, weakest with, gaining fastest in, and
losing fastest in.

All "change" figures are calculated per (category, group, party) series and
are gap-aware: they won't compare across the tracker's mid-2024/early-2025
hiatus (or any other gap) as if it were a normal few weeks.

Every function that takes `trailing_weeks` accepts either a single number
(e.g. `12`) or a list of them (e.g. `[4, 12, 52]`) so you can compare
short-term momentum against the medium- and long-term trend in one go.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_TRAILING_WEEKS = [4, 12, 52]


def _as_week_list(trailing_weeks: int | list[int]) -> list[int]:
    """Normalise a single window or a list of windows into a list of ints."""
    if isinstance(trailing_weeks, (list, tuple, set)):
        weeks = sorted(set(int(w) for w in trailing_weeks))
    else:
        weeks = [int(trailing_weeks)]
    if not weeks:
        raise ValueError("trailing_weeks must contain at least one window")
    return weeks


def _change_col(weeks: int) -> str:
    return f"change_{weeks}w"


def _value_weeks_ago(series: pd.DataFrame, weeks: int, max_slack_ratio: float = 1.5) -> float | None:
    """Value at approximately `weeks` before the series' latest date, using
    the most recent poll at or before that target date. Returns None if no
    poll falls close enough (avoids reaching back across a data gap)."""
    series = series.sort_values("date")
    if series.empty:
        return None
    latest_date = series["date"].iloc[-1]
    target = latest_date - pd.Timedelta(weeks=weeks)
    candidates = series[series["date"] <= target]
    if candidates.empty:
        return None
    base_row = candidates.iloc[-1]
    slack_days = weeks * 7 * max_slack_ratio
    if (target - base_row["date"]).days > slack_days:
        return None
    return float(base_row["value"])


def trend_slope_per_month(series: pd.DataFrame) -> float | None:
    """Ordinary least-squares slope of value vs. time, in percentage points
    per 30 days, fit only to the most recent unbroken segment (see
    loader.flag_gaps). None if fewer than 3 points."""
    series = series.sort_values("date")
    if series.empty:
        return None
    last_segment = series["segment"].iloc[-1]
    seg = series[series["segment"] == last_segment]
    if len(seg) < 3:
        return None
    x = (seg["date"] - seg["date"].min()).dt.days.to_numpy(dtype=float)
    y = seg["value"].to_numpy(dtype=float)
    slope_per_day = np.polyfit(x, y, 1)[0]
    return float(slope_per_day * 30)


def build_summary(
    df: pd.DataFrame, trailing_weeks: int | list[int] = DEFAULT_TRAILING_WEEKS
) -> pd.DataFrame:
    """One row per (category, group, party) with latest support, change
    since the start of the available data, a linear trend (pp/month) fit to
    the current unbroken run of polls, and one `change_{w}w` column for
    every window in `trailing_weeks` -- e.g. pass `[4, 12, 52]` to get
    `change_4w`, `change_12w` and `change_52w` all in the same table.

    A window is left as NaN for a given series if there's no poll close
    enough to that target date (e.g. asking for `change_52w` when a series
    only has 20 weeks of history, or when the window would reach back across
    a data gap) -- so a wide `trailing_weeks` list is always safe to pass
    even when some windows aren't available for every group.
    """
    weeks_list = _as_week_list(trailing_weeks)
    rows = []
    for (cat, grp, party), sub in df.groupby(["category", "group", "party"], sort=False):
        sub = sub.sort_values("date")
        latest_row = sub.iloc[-1]
        first_row = sub.iloc[0]
        row = {
            "category": cat,
            "group": grp,
            "party": party,
            "latest_date": latest_row["date"],
            "latest": latest_row["value"],
            "change_since_start": latest_row["value"] - first_row["value"],
            "trend_pp_per_month": trend_slope_per_month(sub),
            "first_date": first_row["date"],
            "n_polls": len(sub),
        }
        for w in weeks_list:
            prior_value = _value_weeks_ago(sub, w)
            row[_change_col(w)] = (
                (latest_row["value"] - prior_value) if prior_value is not None else np.nan
            )
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values(["category", "party", "group"]).reset_index(drop=True)


def _require_change_cols(summary_df: pd.DataFrame, weeks_list: list[int]) -> None:
    missing = [w for w in weeks_list if _change_col(w) not in summary_df.columns]
    if missing:
        raise KeyError(
            f"summary_df is missing {[_change_col(w) for w in missing]}. "
            f"Re-run build_summary(df, trailing_weeks=...) including {missing}."
        )


def category_leaderboard(
    summary_df: pd.DataFrame, category: str, trailing_weeks: int | list[int] = DEFAULT_TRAILING_WEEKS
) -> pd.DataFrame:
    """For one breakdown category (e.g. "Age"), one row per party showing
    its strongest group, weakest group (window-independent -- based on
    latest support), plus the group gaining/losing fastest *within that
    category* for every window in `trailing_weeks`. Passing e.g.
    `[4, 12, 52]` adds `most_gaining_4w` / `gaining_4w_pp`,
    `most_gaining_12w` / `gaining_12w_pp`, etc., so short- and long-term
    momentum sit side by side in one table.
    """
    from . import config

    weeks_list = _as_week_list(trailing_weeks)
    _require_change_cols(summary_df, weeks_list)

    d = summary_df[summary_df["category"] == category]
    rows = []
    for party, sub in d.groupby("party"):
        sub_latest = sub.dropna(subset=["latest"])
        if sub_latest.empty:
            continue
        strongest = sub_latest.loc[sub_latest["latest"].idxmax()]
        weakest = sub_latest.loc[sub_latest["latest"].idxmin()]
        row = {
            "party": party,
            "strongest": strongest["group"],
            "strongest_%": round(strongest["latest"] * 100, 1),
            "weakest": weakest["group"],
            "weakest_%": round(weakest["latest"] * 100, 1),
        }
        for w in weeks_list:
            chg_col = _change_col(w)
            sub_chg = sub.dropna(subset=[chg_col])
            gaining = sub_chg.loc[sub_chg[chg_col].idxmax()] if not sub_chg.empty else None
            losing = sub_chg.loc[sub_chg[chg_col].idxmin()] if not sub_chg.empty else None
            row[f"most_gaining_{w}w"] = gaining["group"] if gaining is not None else None
            row[f"gaining_{w}w_pp"] = round(gaining[chg_col] * 100, 1) if gaining is not None else None
            row[f"most_losing_{w}w"] = losing["group"] if losing is not None else None
            row[f"losing_{w}w_pp"] = round(losing[chg_col] * 100, 1) if losing is not None else None
        rows.append(row)

    out = pd.DataFrame(rows).set_index("party")
    order = [p for p in config.PARTY_ORDER if p in out.index]
    return out.loc[order]


def headline_table(
    summary_df: pd.DataFrame,
    trailing_weeks: int | list[int] = DEFAULT_TRAILING_WEEKS,
    exclude_categories: tuple[str, ...] = ("Overall",),
) -> pd.DataFrame:
    """One row per party: its single strongest and weakest group *across all
    breakdown categories combined* (window-independent), plus the group
    gaining/losing fastest for every window in `trailing_weeks`. This is the
    direct answer to "which demographic is party X strongest/weakest with,
    and where are they gaining or losing ground -- in the short term vs. the
    long term".
    """
    from . import config

    weeks_list = _as_week_list(trailing_weeks)
    _require_change_cols(summary_df, weeks_list)

    d = summary_df[~summary_df["category"].isin(exclude_categories)]
    rows = []
    for party, sub in d.groupby("party"):
        sub_latest = sub.dropna(subset=["latest"])
        if sub_latest.empty:
            continue
        strongest = sub_latest.loc[sub_latest["latest"].idxmax()]
        weakest = sub_latest.loc[sub_latest["latest"].idxmin()]
        row = {
            "party": party,
            "strongest_group": f"{strongest['category']}: {strongest['group']}",
            "strongest_%": round(strongest["latest"] * 100, 1),
            "weakest_group": f"{weakest['category']}: {weakest['group']}",
            "weakest_%": round(weakest["latest"] * 100, 1),
        }
        for w in weeks_list:
            chg_col = _change_col(w)
            sub_chg = sub.dropna(subset=[chg_col])
            gaining = sub_chg.loc[sub_chg[chg_col].idxmax()] if not sub_chg.empty else None
            losing = sub_chg.loc[sub_chg[chg_col].idxmin()] if not sub_chg.empty else None
            row[f"most_gaining_group_{w}w"] = (
                f"{gaining['category']}: {gaining['group']}" if gaining is not None else None
            )
            row[f"gaining_{w}w_pp"] = round(gaining[chg_col] * 100, 1) if gaining is not None else None
            row[f"most_losing_group_{w}w"] = (
                f"{losing['category']}: {losing['group']}" if losing is not None else None
            )
            row[f"losing_{w}w_pp"] = round(losing[chg_col] * 100, 1) if losing is not None else None
        rows.append(row)

    out = pd.DataFrame(rows).set_index("party")
    order = [p for p in config.PARTY_ORDER if p in out.index]
    return out.loc[order]


def vote_retention_table(
    summary_df: pd.DataFrame, trailing_weeks: int | list[int] = DEFAULT_TRAILING_WEEKS
) -> pd.DataFrame:
    """Return the share of each major party's previous voters who still
    support that party, with changes over each requested window.

    The result uses one row per party and is indexed by party, matching the
    CSV format used by the analysis notebook.
    """
    from . import config

    weeks_list = _as_week_list(trailing_weeks)
    _require_change_cols(summary_df, weeks_list)

    past_vote_labels = {
        "Con": "Conservative",
        "Lab": "Labour",
        "Lib Dem": "Liberal Democrat",
        "Reform UK": "Reform UK",
    }
    past_vote = summary_df[summary_df["category"] == "Past Vote"]
    rows = []
    for party, group in past_vote_labels.items():
        matching = past_vote[(past_vote["party"] == party) & (past_vote["group"] == group)]
        if matching.empty:
            continue
        row = matching.iloc[-1]
        retention = {
            "party": party,
            "latest_date": row["latest_date"],
            "retention_%": round(float(row["latest"]) * 100, 1),
            "n_polls": int(row["n_polls"]),
        }
        for weeks in weeks_list:
            retention[f"{weeks}w_pp"] = (
                round(float(row[f"change_{weeks}w"]) * 100, 1)
                if pd.notna(row[f"change_{weeks}w"])
                else np.nan
            )
        rows.append(retention)

    columns = ["party", "latest_date", "retention_%"]
    columns.extend(f"{weeks}w_pp" for weeks in weeks_list)
    columns.append("n_polls")
    if not rows:
        return pd.DataFrame(columns=columns).set_index("party")

    out = pd.DataFrame(rows).set_index("party")
    order = [party for party in config.PARTY_ORDER if party in out.index]
    return out.loc[order, [column for column in columns if column != "party"]]


def momentum_table(
    summary_df: pd.DataFrame,
    category: str,
    party: str,
    trailing_weeks: int | list[int] = DEFAULT_TRAILING_WEEKS,
) -> pd.DataFrame:
    """One row per group within `category`, columns = change over each
    window in `trailing_weeks` (in percentage points), for a single `party`.
    Lets you see at a glance whether a group's movement is accelerating
    (a bigger 4-week change than you'd expect from the 52-week trend) or
    fading (a small recent change despite a large longer-term move).
    """
    weeks_list = _as_week_list(trailing_weeks)
    _require_change_cols(summary_df, weeks_list)

    d = summary_df[(summary_df["category"] == category) & (summary_df["party"] == party)].copy()
    cols = [_change_col(w) for w in weeks_list]
    out = d.set_index("group")[["latest", *cols]] * 100
    out = out.rename(columns={"latest": "latest_%", **{c: f"{c}_pp" for c in cols}})
    return out.round(1).sort_values(f"{_change_col(weeks_list[-1])}_pp", ascending=False)
