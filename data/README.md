# data/

Drop poll-tracker workbooks here. Each `.xlsx` should have the same layout as
`voting-intention.xlsx`:

- one sheet per demographic breakdown (e.g. `18-24`, `Scotland`, `I voted to Leave`),
- each sheet: rows = `Con`, `Lab`, `Lib Dem`, `SNP`, `Plaid Cymru`, `Reform UK`,
  `Green`, `Other`, `Unweighted base`, `Base`; columns = one weekly poll date each.

The source workbook is not committed to this repository. A local working copy may
contain:

- `voting-intention.xlsx` — 2025-01-13 to 2026-08-03.

## Getting the latest poll

**Easiest:** from the repo root, run `python scripts/update.py` (or the optional
download cell near the top of the notebook). This fetches the current workbook
straight from YouGov's public API and overwrites `voting-intention.xlsx` in place —
no manual downloading or moving files. It's safe to re-run any time: if nothing's
changed since your last download it does nothing. The previous version is copied to
`_archive/` first (see below), keeping a local backup of the previous version.

If your network blocks `yougov.com`, download the file from YouGov in a browser as
before and drop it in here manually — everything downstream works exactly the same
either way.

## `_archive/`

Auto-created by `scripts/fetch_latest_data.py` / `update.py`: a dated backup copy of
`voting-intention.xlsx` is saved here every time a new download actually changes it.
This folder is *not* read by the loader (which only looks at `data/*.xlsx`, not
subfolders), so archived snapshots never cause duplicate rows in the analysis — it's
just a safety net / history of past downloads.

## Still to add

**Still to add:** `voting-intention-2019-2024.xlsx` (mentioned as covering
2019–2024, with a gap before this file's series starts). This is a separate archival
export, not part of YouGov's live tracker download, so it has to be added manually.
Once you add it, just re-run the notebook or `python scripts/refresh_outputs.py` — no
code changes needed as long as its sheet names follow the same pattern. If a sheet
name isn't recognised (e.g. a previous-vote category specific to the 2019 election),
the loader will print a warning naming the sheet rather than dropping it silently —
extend `classify_sheet()` in `src/voting_intention/config.py` to handle it.

The loader also auto-detects gaps between files (e.g. the Jul-2024 → Jan-2025
hiatus) and breaks trend lines there instead of connecting across them.
