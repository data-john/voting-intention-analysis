"""
voting_intention
=================

A small, reusable toolkit for turning weekly voting-intention tracker
workbooks (one sheet per demographic breakdown, one column per poll date)
into a tidy long-format dataset, and for analysing/plotting how support
for each party is moving among different groups (age, gender, region,
past vote, EU referendum vote, social grade, ...).

Typical usage
-------------
    from voting_intention import loader, analysis, plotting

    df = loader.load_all("../data")                 # tidy long dataframe
    summary = analysis.build_summary(df)             # one row per group x party
    headline = analysis.headline_table(summary)      # strongest/weakest/gaining/losing per party

    fig = plotting.plot_category_grid(df, category="Age")
"""

from . import config, loader, analysis, plotting, downloader  # noqa: F401
