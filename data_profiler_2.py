"""
data_profiler.py
----------------
Generates a data profile report for every sheet in one or more Excel files.
Uses ydata-profiling (pandas-profiling) for all statistical computation.

Usage:
    python data_profiler.py file1.xlsx file2.xlsx ...

Output:
    <filename_without_ext>_<sheetname>_profile.html  — one HTML report per sheet.
"""

import sys
from pathlib import Path

import pandas as pd
from ydata_profiling import ProfileReport


def profile_file(path: str) -> list[str]:
    """Profile all sheets in an Excel file; return list of report paths."""
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(f"File not found: {path}")

    sheets: dict[str, pd.DataFrame] = pd.read_excel(fp, sheet_name=None)
    output_paths = []

    for sheet_name, df in sheets.items():
        print(f"  Profiling sheet: {sheet_name}  ({len(df):,} rows x {len(df.columns)} cols)")

        profile = ProfileReport(
            df,
            title=f"{fp.name}  —  {sheet_name}",
            explorative=True,
            progress_bar=False,
        )

        safe_sheet = sheet_name.replace(" ", "_").replace("/", "-")
        out_path = f"{fp.stem}_{safe_sheet}_profile.html"
        profile.to_file(out_path)
        print(f"    -> {out_path}")
        output_paths.append(out_path)

    return output_paths


def main():
    files = sys.argv[1:] or ["Oracle.xlsx", "SQLServer.xlsx"]
    for path in files:
        print(f"\nProfiling: {path}")
        profile_file(path)


if __name__ == "__main__":
    main()
    