"""
Load one or more voting-intention tracker workbooks (each sheet = one
demographic breakdown, rows = parties + sample sizes, columns = weekly poll
dates) into a single tidy long-format DataFrame:

    date | category | group | party | value | unweighted_base | base | sheet | source_file | segment

`value` is the vote share as a fraction (0.32 == 32%).
`segment` increments whenever there's a gap of more than `gap_threshold_days`
between consecutive polls for a given (category, group, party) series --
useful so plots don't draw a misleading straight line across, e.g., the
Jul-2024 to Jan-2025 hiatus between tracker waves.

Adding new data
----------------
Drop any additional workbook(s) with the same sheet layout into the data
folder and call `load_all()` again -- no code changes needed as long as the
sheet names are recognised by `config.classify_sheet` (see config.py).
"""
from __future__ import annotations

import glob
import os
import warnings

import pandas as pd

from . import config

PARTY_ROWS = ["Con", "Lab", "Lib Dem", "SNP", "Plaid Cymru", "Reform UK", "Green", "Other"]
BASE_ROWS = {"Unweighted base": "unweighted_base", "Base": "base"}


def find_data_files(data_dir: str) -> list[str]:
    """Return every .xlsx in `data_dir`, ignoring Excel's temporary lock files."""
    files = sorted(glob.glob(os.path.join(data_dir, "*.xlsx")))
    return [f for f in files if not os.path.basename(f).startswith("~$")]


def _load_sheet(df_raw: pd.DataFrame, sheet_name: str, source_file: str) -> pd.DataFrame:
    category, group = config.classify_sheet(sheet_name)
    if category == "Other/Unclassified":
        warnings.warn(
            f"Sheet '{sheet_name}' in {os.path.basename(source_file)} could not be "
            "classified automatically -- extend classify_sheet() in config.py. "
            "Its rows are kept under category='Other/Unclassified' so nothing is lost."
        )

    df_raw = df_raw.copy()
    df_raw.index = df_raw.index.astype(str).str.strip()

    dates = pd.to_datetime(df_raw.columns, errors="coerce")
    keep = ~dates.isna()
    df_raw = df_raw.loc[:, keep]
    df_raw.columns = dates[keep]

    present_parties = [p for p in PARTY_ROWS if p in df_raw.index]
    if not present_parties:
        return pd.DataFrame(
            columns=["date", "party", "value", "category", "group", "sheet", "source_file"]
        )

    party_block = df_raw.loc[present_parties].copy()
    party_block.index.name = "party"
    long = party_block.reset_index().melt(id_vars="party", var_name="date", value_name="value")
    long["date"] = pd.to_datetime(long["date"])
    long["value"] = pd.to_numeric(long["value"], errors="coerce")
    long = long.dropna(subset=["value"])

    base_series = []
    for row_label, col_name in BASE_ROWS.items():
        if row_label in df_raw.index:
            base_series.append(df_raw.loc[row_label].rename(col_name))
    if base_series:
        base_df = pd.concat(base_series, axis=1)
        base_df.index.name = "date"
        base_df = base_df.reset_index()
        long = long.merge(base_df, on="date", how="left")

    long["category"] = category
    long["group"] = group
    long["sheet"] = sheet_name
    long["source_file"] = os.path.basename(source_file)
    return long


def load_workbook_long(path: str) -> pd.DataFrame:
    """Load a single workbook (all sheets) into tidy long format."""
    with pd.ExcelFile(path) as xls:
        frames = [
            _load_sheet(pd.read_excel(xls, sheet_name=sheet, header=0, index_col=0), sheet, path)
            for sheet in xls.sheet_names
        ]
    return pd.concat(frames, ignore_index=True)


def flag_gaps(df: pd.DataFrame, gap_threshold_days: int = 21) -> pd.DataFrame:
    """Add a `segment` id per (category, group, party) series, incrementing
    each time the gap since the previous poll exceeds `gap_threshold_days`
    (default 3 weeks -- these trackers normally run weekly)."""
    df = df.sort_values(["category", "group", "party", "date"]).copy()
    keys = [df["category"], df["group"], df["party"]]
    gap_days = df.groupby(keys, sort=False)["date"].diff().dt.days
    new_segment = gap_days.isna() | (gap_days > gap_threshold_days)
    df["segment"] = new_segment.groupby(keys).cumsum().astype(int)
    return df


def load_all(data_dir: str = "data", files: list[str] | None = None, gap_threshold_days: int = 21) -> pd.DataFrame:
    """Load every workbook in `data_dir` (or an explicit `files` list),
    combine them, resolve any overlapping dates, and flag gaps for plotting.
    """
    if files is None:
        files = find_data_files(data_dir)
    if not files:
        raise FileNotFoundError(
            f"No .xlsx files found in {data_dir!r}. Add poll-tracker workbook(s) there."
        )

    combined = pd.concat([load_workbook_long(f) for f in files], ignore_index=True)

    # If the same (date, category, group, party) appears in more than one
    # file -- e.g. overlapping weeks between an old and a refreshed export --
    # keep the value from whichever file was modified most recently on disk.
    file_order = {
        os.path.basename(f): rank
        for rank, f in enumerate(sorted(files, key=os.path.getmtime))
    }
    combined["_file_rank"] = combined["source_file"].map(file_order)
    combined = combined.sort_values(
        ["date", "category", "group", "party", "_file_rank"]
    ).drop_duplicates(subset=["date", "category", "group", "party"], keep="last")
    combined = combined.drop(columns="_file_rank").reset_index(drop=True)

    combined = flag_gaps(combined, gap_threshold_days=gap_threshold_days)
    return combined


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """One row per source file: date range and number of polls covered --
    handy for sanity-checking that a newly-added file was picked up, and for
    spotting gaps between files."""
    rep = (
        df.groupby("source_file")
        .agg(first_date=("date", "min"), last_date=("date", "max"), n_rows=("date", "size"))
        .sort_values("first_date")
    )
    return rep
