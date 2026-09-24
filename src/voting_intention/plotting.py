"""
Reusable matplotlib/seaborn chart functions for the voting-intention
dataset. Every function takes the tidy long DataFrame (or the summary table
from `analysis.build_summary`) and returns a matplotlib Figure, optionally
saving it to disk. Nothing here holds state, so cells can be re-run freely
as new data is added.
"""
from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from . import config

_STYLED = False


def _apply_style():
    global _STYLED
    if _STYLED:
        return
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.grid": True,
            "grid.alpha": 0.25,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.titleweight": "bold",
        }
    )
    _STYLED = True


def _pct_formatter(x, _pos=None):
    return f"{x:.0f}%"


def plot_group_lines(
    ax,
    df: pd.DataFrame,
    category: str,
    group: str,
    parties: list[str] | None = None,
    smooth_weeks: int | None = 4,
    show_raw: bool = True,
    legend: bool = False,
):
    """Draw one line per party (for a single category/group) onto `ax`.
    Thin, translucent lines show the raw weekly poll; a bold line shows the
    `smooth_weeks`-poll rolling average. Series are split at gaps (see
    loader.flag_gaps) so no line is drawn across missing weeks."""
    _apply_style()
    parties = parties or config.PARTY_ORDER
    sub = df[(df["category"] == category) & (df["group"] == group) & (df["party"].isin(parties))]

    for party in parties:
        s = sub[sub["party"] == party].sort_values("date")
        if s.empty:
            continue
        color = config.PARTY_COLORS.get(party, "#333333")
        label_used = False
        for _, seg in s.groupby("segment"):
            if len(seg) == 0:
                continue
            if show_raw:
                ax.plot(seg["date"], seg["value"] * 100, color=color, alpha=0.22, linewidth=1)
            if smooth_weeks and len(seg) >= 2:
                sm = seg.set_index("date")["value"].rolling(smooth_weeks, min_periods=1).mean() * 100
                ax.plot(
                    sm.index,
                    sm.values,
                    color=color,
                    linewidth=2,
                    label=(party if not label_used else None),
                )
            else:
                ax.plot(
                    seg["date"],
                    seg["value"] * 100,
                    color=color,
                    linewidth=2,
                    label=(party if not label_used else None),
                )
            label_used = True

    ax.set_title(group)
    ax.yaxis.set_major_formatter(_pct_formatter)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.tick_params(axis="x", rotation=45)
    if legend:
        ax.legend(fontsize=8, frameon=False)


def plot_overall_trend(
    df: pd.DataFrame,
    parties: list[str] | None = None,
    smooth_weeks: int = 4,
    figsize=(10, 5),
    save_path: str | None = None,
):
    """Headline national trend chart (category='Overall', group='All adults')."""
    _apply_style()
    fig, ax = plt.subplots(figsize=figsize)
    plot_group_lines(ax, df, "Overall", "All adults", parties=parties, smooth_weeks=smooth_weeks, legend=True)
    ax.set_title(f"National voting intention  (bold = {smooth_weeks}-week average)")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_category_grid(
    df: pd.DataFrame,
    category: str,
    parties: list[str] | None = None,
    smooth_weeks: int = 4,
    figsize: tuple | None = None,
    ncols: int = 3,
    save_path: str | None = None,
):
    """Small-multiples figure: one subplot per group within `category`, each
    showing every party's trend line for that group."""
    _apply_style()
    parties = parties or config.MAIN_PARTIES
    groups = config.order_groups(category, df.loc[df["category"] == category, "group"].unique())
    n = len(groups)
    ncols = min(ncols, n) or 1
    nrows = -(-n // ncols)

    fig, axes = plt.subplots(nrows, ncols, figsize=figsize or (4.6 * ncols, 3.0 * nrows), sharey=True)
    axes = np.atleast_1d(axes).ravel()

    handles_labels = None
    for ax, group in zip(axes, groups):
        plot_group_lines(ax, df, category, group, parties=parties, smooth_weeks=smooth_weeks)
        if handles_labels is None:
            handles_labels = ax.get_legend_handles_labels()
    for ax in axes[len(groups):]:
        ax.axis("off")

    fig.suptitle(
        f"Voting intention by {category}  (thin = weekly poll, bold = {smooth_weeks}-week average)",
        fontsize=13,
    )
    if handles_labels and handles_labels[0]:
        fig.legend(
            *handles_labels,
            loc="lower center",
            ncol=min(8, len(handles_labels[0])),
            frameon=False,
            bbox_to_anchor=(0.5, -0.02),
        )
    fig.tight_layout(rect=[0, 0.05, 1, 0.95])
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_latest_heatmap(
    summary_df: pd.DataFrame,
    exclude_categories: tuple[str, ...] = ("Overall",),
    parties: list[str] | None = None,
    figsize: tuple | None = None,
    save_path: str | None = None,
):
    """Heatmap of latest support (rows = every group across all breakdown
    categories, columns = party). Colour shows each group's support
    *relative to that party's own average* (a z-score down the column), so
    a party's genuinely strong/weak groups stand out even though parties
    differ hugely in overall level; the cell text is always the real %."""
    _apply_style()
    parties = parties or config.PARTY_ORDER
    d = summary_df[~summary_df["category"].isin(exclude_categories) & summary_df["party"].isin(parties)].copy()
    d["label"] = d["category"] + ": " + d["group"]

    pivot_pct = d.pivot_table(index="label", columns="party", values="latest") * 100
    pivot_pct = pivot_pct[[p for p in config.PARTY_ORDER if p in pivot_pct.columns]]

    z = pivot_pct.apply(lambda col: (col - col.mean()) / col.std(ddof=0) if col.std(ddof=0) else col * 0)
    annot = pivot_pct.round(0).astype("Int64").astype(str) + "%"

    fig, ax = plt.subplots(figsize=figsize or (1.15 * len(pivot_pct.columns) + 2.5, 0.4 * len(pivot_pct) + 2))
    sns.heatmap(
        z,
        annot=annot,
        fmt="",
        cmap="RdBu_r",
        center=0,
        cbar_kws={"label": "Relative strength within party (z-score across groups)"},
        linewidths=0.4,
        linecolor="white",
        ax=ax,
    )
    ax.set_title("Latest support by group and party\n(colour = strong/weak relative to that party's own average)")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def _change_pivot(
    summary_df: pd.DataFrame, trailing_weeks: int, exclude_categories: tuple[str, ...], parties: list[str]
) -> pd.DataFrame:
    chg_col = f"change_{trailing_weeks}w"
    if chg_col not in summary_df.columns:
        raise KeyError(
            f"summary_df has no '{chg_col}' column -- build it with "
            f"analysis.build_summary(df, trailing_weeks=... including {trailing_weeks})."
        )
    d = summary_df[~summary_df["category"].isin(exclude_categories) & summary_df["party"].isin(parties)].copy()
    d["label"] = d["category"] + ": " + d["group"]
    pivot = d.pivot_table(index="label", columns="party", values=chg_col) * 100
    return pivot[[p for p in config.PARTY_ORDER if p in pivot.columns]]


def _draw_change_heatmap(ax, pivot: pd.DataFrame, title: str, cbar: bool = True):
    vmax = np.nanmax(np.abs(pivot.values)) if np.isfinite(pivot.values).any() else 1
    sns.heatmap(
        pivot,
        annot=True,
        fmt="+.1f",
        cmap="RdBu_r",
        center=0,
        vmin=-vmax,
        vmax=vmax,
        cbar=cbar,
        cbar_kws={"label": "Change (pp)"} if cbar else None,
        linewidths=0.4,
        linecolor="white",
        ax=ax,
    )
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel("")


def plot_change_heatmap(
    summary_df: pd.DataFrame,
    trailing_weeks: int = 12,
    exclude_categories: tuple[str, ...] = ("Overall",),
    parties: list[str] | None = None,
    figsize: tuple | None = None,
    save_path: str | None = None,
):
    """Heatmap of change in support over a single trailing window (in
    percentage points), diverging around zero -- shows at a glance which
    groups are moving towards / away from each party. For several windows
    side by side (e.g. 4 vs 12 vs 52 weeks), use `plot_change_heatmap_grid`."""
    _apply_style()
    parties = parties or config.PARTY_ORDER
    pivot = _change_pivot(summary_df, trailing_weeks, exclude_categories, parties)

    fig, ax = plt.subplots(figsize=figsize or (1.15 * len(pivot.columns) + 2.5, 0.4 * len(pivot) + 2))
    _draw_change_heatmap(ax, pivot, f"Change in support by group and party, last {trailing_weeks} weeks")
    fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_change_heatmap_grid(
    summary_df: pd.DataFrame,
    trailing_weeks: list[int] = (4, 12, 52),
    exclude_categories: tuple[str, ...] = ("Overall",),
    parties: list[str] | None = None,
    figsize: tuple | None = None,
    save_path: str | None = None,
):
    """Several change heatmaps side by side, one per window in
    `trailing_weeks` (e.g. `[4, 12, 52]` for short/medium/long-term
    momentum). Each panel has its own colour scale, since a 52-week change
    is typically much larger in magnitude than a 4-week one -- read the
    colour within a panel, and the printed number across panels."""
    _apply_style()
    parties = parties or config.PARTY_ORDER
    windows = list(trailing_weeks)
    pivots = [_change_pivot(summary_df, w, exclude_categories, parties) for w in windows]
    n_rows = len(pivots[0].index) if pivots else 0

    fig, axes = plt.subplots(
        1, len(windows), figsize=figsize or (1.05 * len(parties) * len(windows) + 3, 0.4 * n_rows + 2), sharey=True
    )
    axes = np.atleast_1d(axes)
    for ax, w, pivot in zip(axes, windows, pivots):
        _draw_change_heatmap(ax, pivot, f"Last {w} weeks")
        ax.set_ylabel("")
    axes[0].tick_params(axis="y", labelrotation=0)

    fig.suptitle("Change in support by group and party, across windows", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig
