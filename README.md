# Voting Intention Tracker — Analysis

Turns weekly UK voting-intention tracker workbooks (one sheet per demographic
breakdown — age, gender, region, past vote, EU referendum vote, social grade)
into a tidy dataset, then analyses and charts how support for each party is
moving among different groups: who each party is **strongest** and **weakest**
with, and where it's currently **gaining** or **losing** ground.

## Structure

```
data/                    Poll-tracker workbooks (.xlsx) live here — see data/README.md
  _archive/                 Auto-created backups of previous downloads (ignored by the loader)
src/voting_intention/    Reusable library
  config.py                Party metadata, colours, and sheet-name -> (category, group) mapping
  loader.py                Reads workbook(s) into one tidy long-format DataFrame
  downloader.py             Downloads the latest tracker workbook from YouGov
  analysis.py               Summary stats + strongest/weakest/gaining/losing tables
  plotting.py               Reusable matplotlib/seaborn chart functions
notebooks/
  01_voting_intention_analysis.ipynb   Interactive analysis notebook
scripts/
  update.py                   Fetch the latest data AND regenerate everything (one command)
  fetch_latest_data.py         Just download the latest workbook into data/
  refresh_outputs.py           Just regenerate every chart/table from what's already in data/
  build_site.py                Build the static public report from outputs/
web/
  styles.css                   Report styling copied into the generated site
outputs/
  figures/                    Saved PNG charts
  tables/                     Saved CSV summary tables
site/                         Generated static site (ignored by Git)
```

## Setup

```bash
pip install -r requirements.txt
```

## Usage

**When a new poll comes out**, from the repo root:

```bash
python scripts/update.py
```

This downloads the latest workbook straight from YouGov into `data/voting-intention.xlsx`
and regenerates every chart and table. It's safe to run any time — if there's no new
poll since your last download, it reuses the existing workbook and refreshes the outputs.

The source workbook is not committed to this repository. On a fresh checkout, run
`python scripts/fetch_latest_data.py` to download it, or use `python scripts/update.py`
to download the workbook and regenerate the saved charts and tables in one step.

Or do it from within the notebook: `notebooks/01_voting_intention_analysis.ipynb` has an
optional cell near the top that calls the same downloader before loading the data.

**Interactively (recommended for exploring):**

```bash
jupyter notebook notebooks/01_voting_intention_analysis.ipynb
```

Saved charts and tables are available under `outputs/`; the notebook's saved cell
outputs are cleared to keep the notebook compact.

**From the command line, fetch and refresh separately if you prefer:**

```bash
python scripts/fetch_latest_data.py           # just download
python scripts/refresh_outputs.py             # just regenerate charts/tables
python scripts/refresh_outputs.py --weeks 4 12 52    # customise the trailing windows
```

`refresh_outputs.py` and `update.py` load every workbook in `data/`, build the summary
tables, and (re)write every chart to `outputs/figures/` and every table to
`outputs/tables/`, including `vote_retention.csv`. `fetch_latest_data.py` only downloads
the workbook.

## Public report and weekly publishing

The static report is built from the saved charts and CSV tables:

```bash
python scripts/build_site.py
```

This writes the report at both the site root and `site/yougov/`, with chart assets
and CSV downloads alongside each copy. That makes the report available at
`electionmodels.com/yougov/` while keeping the root report in place. The generated
`site/` directory is ignored by Git. Open it locally with
`python -m http.server --directory site` if you want to preview it.

`.github/workflows/publish-report.yml` checks YouGov each morning at 08:17 UK time,
also runs when changes are pushed to `main`, and supports a manual run from the GitHub
Actions tab. It fetches the workbook in the temporary runner, runs `scripts/update.py`,
builds the report, and deploys the static artifact to GitHub Pages. The workbook and
archive are not committed or included in the site. A failed download or build stops the
workflow before deployment, leaving the last successful report in place.

### One-time GitHub Pages and domain setup

1. In the repository's **Settings → Pages**, select **GitHub Actions** as the build and
   deployment source.
2. Verify `electionmodels.com` under the account's GitHub Pages domain settings, then
   set `electionmodels.com` as the repository's custom domain.
3. In the domain's DNS control panel, point the apex (`@`) to GitHub Pages with the four
   A records listed in [GitHub's custom-domain instructions](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-your-custom-domain-for-your-github-pages-site).
   Add a `www` CNAME pointing to `data-john.github.io` so GitHub Pages redirects it to
   the apex domain.
4. After DNS has propagated and GitHub has provisioned its certificate, enable
   **Enforce HTTPS** in the Pages settings.

The workflow publishes to the repository's default GitHub Pages address until the
custom domain is configured. GitHub Pages may take some time to verify DNS and make
HTTPS available.

## Where the data comes from

`scripts/fetch_latest_data.py` (and `update.py`) download directly from YouGov's public
tracker API:

```
https://api-test.yougov.com/public-data/v5/uk/trackers/voting-intention/download/
```

This always returns the *full* current workbook (every week to date), so the download
overwrites `data/voting-intention.xlsx` in place rather than piling up one file per
poll. The previous version is copied to `data/_archive/` first, so nothing is lost —
that folder is outside the loader's search path (`data/*.xlsx` only), so archived
copies never cause duplicate rows in the analysis. If your organisation's network
blocks `yougov.com`, download the file in a browser as before and drop it into `data/`
manually — everything else works exactly the same either way.

## Adding new poll waves

Just add the new `.xlsx` export to `data/` (same sheet-per-breakdown layout)
and re-run either of the above. The loader:

- picks up every workbook in `data/` automatically,
- classifies each sheet into a breakdown category + group (`src/voting_intention/config.py`),
  warning you by name if it meets a sheet it doesn't recognise rather than
  dropping it,
- de-duplicates any dates that appear in more than one file, and
- flags gaps between polling waves so trend lines don't get drawn across a
  hiatus (e.g. the mid-2024 to Jan-2025 gap between the two source files).

## Data model

`loader.load_all()` returns one row per (date, breakdown category, group,
party):

| column | meaning |
|---|---|
| `date` | poll date |
| `category` | breakdown type, e.g. `Age`, `Region`, `Past Vote` |
| `group` | value within that breakdown, e.g. `18-24`, `Scotland`, `Labour` |
| `party` | `Con`, `Lab`, `Lib Dem`, `SNP`, `Plaid Cymru`, `Reform UK`, `Green`, `Other` |
| `value` | vote share as a fraction (0.32 = 32%) |
| `unweighted_base` / `base` | sample sizes for that poll/breakdown |
| `segment` | increments across data gaps — group by this before drawing a line |

`analysis.build_summary()` collapses that into one row per (category, group,
party) with the latest value, change since the data began, a linear trend
(pp/month), and — because `trailing_weeks` accepts either a single number or
a list — one `change_{w}w` column for **every** window you ask for, e.g.
`build_summary(df, trailing_weeks=[4, 12, 52])` gives you `change_4w`,
`change_12w` and `change_52w` side by side in the same table, so you can
compare short-term momentum against the medium- and long-term trend.

`analysis.headline_table()` and `analysis.category_leaderboard()` take the
same `trailing_weeks` argument and add a `most_gaining_{w}w` /
`gaining_{w}w_pp` / `most_losing_{w}w` / `losing_{w}w_pp` set of columns per
window ("strongest"/"weakest" stay window-independent, since they're based
on latest support only). `analysis.momentum_table()` is a narrower view: one
party within one category, every group as a row, one column per window.

For charts, `plotting.plot_change_heatmap()` takes a single window;
`plotting.plot_change_heatmap_grid()` takes a list and draws one panel per
window (each with its own colour scale, since a 52-week change is typically
much bigger in magnitude than a 4-week one).

Reduce further to one row per party: its single strongest/weakest group and
fastest gaining/losing group(s), across all breakdowns (or restricted to
genuine demographics via `exclude_categories=("Overall", "Past Vote")`,
since a party's own past voters are trivially its "strongest" group).

## Notes on the current data

- Source file `voting-intention.xlsx` covers weekly polls from 2025-01-13 to
  2026-08-03.
- A second file, `voting-intention-2019-2024.xlsx`, is referenced but not yet
  in `data/` — see `data/README.md`. Once added, the same notebook/script
  will incorporate it automatically, and the loader will flag the gap between
  the two files' coverage rather than connecting a line across it.
