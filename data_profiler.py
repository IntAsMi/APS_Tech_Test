"""
data_profiler.py
----------------
Generates a data profile report for every sheet in one or more Excel files.
Uses polars for all statistical computation.

Usage:
    python data_profiler.py file1.xlsx file2.xlsx ...

Output:
    <filename_without_ext>_profile.html  — one HTML report per input file,
    containing one section per sheet.
"""

import sys
import math
from pathlib import Path
from datetime import datetime

import polars as pl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(v):
    """Format a scalar for display."""
    if v is None:
        return "—"
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return "—"
        if abs(v) >= 1_000_000:
            return f"{v:,.2f}"
        if abs(v) >= 1:
            return f"{v:,.4f}".rstrip("0").rstrip(".")
        return f"{v:.6f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _pct(n, total):
    if total == 0:
        return "0.0 %"
    return f"{100 * n / total:.1f} %"


# ---------------------------------------------------------------------------
# Per-column profile
# ---------------------------------------------------------------------------

def profile_column(series: pl.Series, total_rows: int) -> dict:
    dtype = series.dtype
    name  = series.name

    null_count    = series.null_count()
    non_null      = total_rows - null_count
    unique_count  = series.n_unique()          # includes null as one category
    distinct_non_null = series.drop_nulls().n_unique()

    base = {
        "column":          name,
        "dtype":           str(dtype),
        "total_rows":      total_rows,
        "null_count":      null_count,
        "null_pct":        _pct(null_count, total_rows),
        "non_null_count":  non_null,
        "unique_count":    distinct_non_null,
        "unique_pct":      _pct(distinct_non_null, non_null) if non_null else "—",
        # numeric stats (filled below for numeric columns)
        "min": None, "max": None, "mean": None, "median": None,
        "std": None, "p25": None, "p75": None, "zeros": None, "negatives": None,
        # string stats
        "min_len": None, "max_len": None, "avg_len": None,
        # top values always present
        "top_values": [],
    }

    s = series.drop_nulls()

    # ---- Numeric -----------------------------------------------------------
    if dtype in (pl.Int8, pl.Int16, pl.Int32, pl.Int64,
                 pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                 pl.Float32, pl.Float64):
        if len(s) > 0:
            s_f = s.cast(pl.Float64)
            base["min"]       = _fmt(s_f.min())
            base["max"]       = _fmt(s_f.max())
            base["mean"]      = _fmt(s_f.mean())
            base["median"]    = _fmt(s_f.median())
            base["std"]       = _fmt(s_f.std())
            base["p25"]       = _fmt(s_f.quantile(0.25, interpolation="nearest"))
            base["p75"]       = _fmt(s_f.quantile(0.75, interpolation="nearest"))
            base["zeros"]     = int((s_f == 0).sum())
            base["negatives"] = int((s_f < 0).sum())

    # ---- String ------------------------------------------------------------
    elif dtype == pl.String or dtype == pl.Utf8:
        if len(s) > 0:
            lengths = s.str.len_chars()
            base["min_len"] = _fmt(lengths.min())
            base["max_len"] = _fmt(lengths.max())
            base["avg_len"] = _fmt(lengths.mean())

    # ---- Date / Datetime ---------------------------------------------------
    elif dtype in (pl.Date, pl.Datetime):
        if len(s) > 0:
            base["min"] = str(s.min())
            base["max"] = str(s.max())

    # ---- Top values --------------------------------------------------------
    if len(s) > 0:
        vc = (
            s.value_counts(sort=True)
             .head(10)
        )
        # value_counts returns a DataFrame with columns [<name>, "count"]
        val_col   = vc.columns[0]
        count_col = vc.columns[1]
        base["top_values"] = [
            (str(row[val_col]), row[count_col])
            for row in vc.iter_rows(named=True)
        ]

    return base


# ---------------------------------------------------------------------------
# Sheet profile
# ---------------------------------------------------------------------------

def profile_sheet(df: pl.DataFrame) -> list[dict]:
    total = len(df)
    return [profile_column(df[col], total) for col in df.columns]


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

CSS = """
:root {
    --bg:      #f8f9fb;
    --card:    #ffffff;
    --border:  #dde1e8;
    --hdr-bg:  #1e3a5f;
    --hdr-fg:  #ffffff;
    --accent:  #2a6496;
    --muted:   #6b7280;
    --pill-num:#dbeafe;
    --pill-str:#dcfce7;
    --pill-dt: #fef9c3;
    --pill-oth:#f3e8ff;
    --warn:    #fef3c7;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: Arial, sans-serif; background: var(--bg);
       color: #1f2937; font-size: 13px; }
header { background: var(--hdr-bg); color: var(--hdr-fg);
         padding: 18px 28px; }
header h1 { font-size: 1.4rem; font-weight: 700; }
header p  { opacity: .75; font-size: .85rem; margin-top: 3px; }
nav { display: flex; gap: 8px; padding: 14px 28px;
      flex-wrap: wrap; border-bottom: 1px solid var(--border);
      background: var(--card); }
nav a { text-decoration: none; color: var(--accent);
        font-weight: 600; font-size: .82rem;
        padding: 4px 10px; border-radius: 999px;
        border: 1px solid var(--accent); }
nav a:hover { background: var(--accent); color: #fff; }
main { padding: 24px 28px; display: flex; flex-direction: column; gap: 36px; }
.sheet-block { scroll-margin-top: 12px; }
.sheet-title { font-size: 1.05rem; font-weight: 700; color: var(--hdr-bg);
               border-left: 4px solid var(--accent);
               padding-left: 10px; margin-bottom: 14px; }
.overview-grid { display: grid; grid-template-columns: repeat(auto-fill,160px);
                 gap: 10px; margin-bottom: 18px; }
.stat-card { background: var(--card); border: 1px solid var(--border);
             border-radius: 8px; padding: 12px 14px; }
.stat-card .label { font-size: .72rem; color: var(--muted);
                    text-transform: uppercase; letter-spacing: .04em; }
.stat-card .value { font-size: 1.3rem; font-weight: 700;
                    color: var(--hdr-bg); margin-top: 2px; }
table { width: 100%; border-collapse: collapse; background: var(--card);
        border-radius: 8px; overflow: hidden;
        border: 1px solid var(--border); font-size: 12px; }
thead tr { background: var(--hdr-bg); color: var(--hdr-fg); }
th { padding: 8px 10px; text-align: left; font-weight: 600;
     white-space: nowrap; font-size: 11px; letter-spacing: .03em; }
td { padding: 7px 10px; border-bottom: 1px solid var(--border);
     vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:nth-child(even) td { background: #f5f7fa; }
.pill { display: inline-block; padding: 1px 7px; border-radius: 999px;
        font-size: 10px; font-weight: 700; letter-spacing: .03em; }
.pill-num { background: var(--pill-num); color: #1d4ed8; }
.pill-str { background: var(--pill-str); color: #15803d; }
.pill-dt  { background: var(--pill-dt);  color: #92400e; }
.pill-oth { background: var(--pill-oth); color: #7c3aed; }
.warn { background: var(--warn); }
.top-val { font-size: 10px; color: var(--muted); }
.top-val span { color: #1f2937; font-weight: 600; }
footer { text-align: center; padding: 20px; color: var(--muted);
         font-size: 11px; border-top: 1px solid var(--border); }
"""

def _dtype_pill(dtype_str: str) -> str:
    d = dtype_str.lower()
    if any(x in d for x in ("int", "float", "uint")):
        cls, lbl = "pill-num", "numeric"
    elif any(x in d for x in ("str", "utf", "cat")):
        cls, lbl = "pill-str", "string"
    elif any(x in d for x in ("date", "time", "duration")):
        cls, lbl = "pill-dt", "datetime"
    else:
        cls, lbl = "pill-oth", dtype_str
    return f'<span class="pill {cls}">{lbl}</span><br><small>{dtype_str}</small>'


def _null_cell(null_pct: str, null_count: int) -> str:
    pct_val = float(null_pct.replace(" %", ""))
    cls = " warn" if pct_val > 10 else ""
    return f'<td class="{cls.strip()}">{null_count:,}<br><small>{null_pct}</small></td>'


def _top_values_cell(top_values: list) -> str:
    if not top_values:
        return "<td>—</td>"
    lines = []
    for val, cnt in top_values[:5]:
        short = (val[:30] + "…") if len(val) > 30 else val
        lines.append(f'<span><b>{short}</b> ({cnt:,})</span>')
    return '<td class="top-val">' + "<br>".join(lines) + "</td>"


def render_sheet_section(sheet_name: str, profiles: list[dict]) -> str:
    total_rows = profiles[0]["total_rows"] if profiles else 0
    total_cols = len(profiles)
    total_nulls = sum(p["null_count"] for p in profiles)
    fully_null  = sum(1 for p in profiles if p["null_count"] == total_rows)
    unique_cols = sum(1 for p in profiles
                      if p["unique_count"] == p["non_null_count"]
                      and p["non_null_count"] > 0)

    overview = f"""
    <div class="overview-grid">
      <div class="stat-card"><div class="label">Rows</div>
        <div class="value">{total_rows:,}</div></div>
      <div class="stat-card"><div class="label">Columns</div>
        <div class="value">{total_cols:,}</div></div>
      <div class="stat-card"><div class="label">Total Nulls</div>
        <div class="value">{total_nulls:,}</div></div>
      <div class="stat-card"><div class="label">Fully-Null Cols</div>
        <div class="value">{fully_null}</div></div>
      <div class="stat-card"><div class="label">Unique-Key Cols</div>
        <div class="value">{unique_cols}</div></div>
    </div>
    """

    # Separate numeric vs non-numeric
    numeric_profiles = [p for p in profiles
                        if any(x in p["dtype"].lower()
                               for x in ("int", "float", "uint"))]
    other_profiles   = [p for p in profiles if p not in numeric_profiles]

    def col_table(profs, is_numeric):
        if not profs:
            return ""
        if is_numeric:
            header = """<tr>
              <th>#</th><th>Column</th><th>Type</th>
              <th>Nulls</th><th>Unique</th>
              <th>Min</th><th>Max</th><th>Mean</th><th>Median</th>
              <th>Std</th><th>P25</th><th>P75</th>
              <th>Zeros</th><th>Negatives</th><th>Top 5 Values</th>
            </tr>"""
            rows = []
            for i, p in enumerate(profs, 1):
                rows.append(f"""<tr>
                  <td>{i}</td>
                  <td><b>{p['column']}</b></td>
                  <td>{_dtype_pill(p['dtype'])}</td>
                  {_null_cell(p['null_pct'], p['null_count'])}
                  <td>{p['unique_count']:,}<br><small>{p['unique_pct']}</small></td>
                  <td>{p['min'] or '—'}</td><td>{p['max'] or '—'}</td>
                  <td>{p['mean'] or '—'}</td><td>{p['median'] or '—'}</td>
                  <td>{p['std'] or '—'}</td>
                  <td>{p['p25'] or '—'}</td><td>{p['p75'] or '—'}</td>
                  <td>{_fmt(p['zeros'])}</td><td>{_fmt(p['negatives'])}</td>
                  {_top_values_cell(p['top_values'])}
                </tr>""")
        else:
            header = """<tr>
              <th>#</th><th>Column</th><th>Type</th>
              <th>Nulls</th><th>Unique</th>
              <th>Min / Earliest</th><th>Max / Latest</th>
              <th>Min Len</th><th>Max Len</th><th>Avg Len</th>
              <th>Top 5 Values</th>
            </tr>"""
            rows = []
            for i, p in enumerate(profs, 1):
                rows.append(f"""<tr>
                  <td>{i}</td>
                  <td><b>{p['column']}</b></td>
                  <td>{_dtype_pill(p['dtype'])}</td>
                  {_null_cell(p['null_pct'], p['null_count'])}
                  <td>{p['unique_count']:,}<br><small>{p['unique_pct']}</small></td>
                  <td>{p['min'] or '—'}</td><td>{p['max'] or '—'}</td>
                  <td>{p['min_len'] or '—'}</td>
                  <td>{p['max_len'] or '—'}</td>
                  <td>{p['avg_len'] or '—'}</td>
                  {_top_values_cell(p['top_values'])}
                </tr>""")

        return (f'<table><thead>{header}</thead>'
                f'<tbody>{"".join(rows)}</tbody></table>')

    num_html   = col_table(numeric_profiles, True)
    other_html = col_table(other_profiles, False)

    num_section = (
        f'<h4 style="margin:14px 0 8px;color:#374151;">Numeric Columns '
        f'({len(numeric_profiles)})</h4>{num_html}'
        if numeric_profiles else ""
    )
    other_section = (
        f'<h4 style="margin:14px 0 8px;color:#374151;">String / Date Columns '
        f'({len(other_profiles)})</h4>{other_html}'
        if other_profiles else ""
    )

    return f"""
    <section class="sheet-block" id="{sheet_name}">
      <div class="sheet-title">Sheet: {sheet_name}</div>
      {overview}
      {num_section}
      {other_section}
    </section>
    """


def render_html(file_name: str, sheet_profiles: dict[str, list[dict]]) -> str:
    nav_links = "".join(
        f'<a href="#{name}">{name}</a>'
        for name in sheet_profiles
    )
    sections = "".join(
        render_sheet_section(name, profs)
        for name, profs in sheet_profiles.items()
    )
    generated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Data Profile — {file_name}</title>
  <style>{CSS}</style>
</head>
<body>
  <header>
    <h1>📊 Data Profile Report</h1>
    <p>{file_name} &nbsp;·&nbsp; Generated {generated}</p>
  </header>
  <nav>{nav_links}</nav>
  <main>{sections}</main>
  <footer>Generated by data_profiler.py using Polars</footer>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def profile_file(path: str) -> str:
    """Profile all sheets in an Excel file; return path to HTML report."""
    fp = Path(path)
    if not fp.exists():
        raise FileNotFoundError(f"File not found: {path}")

    # Read all sheets with pandas (openpyxl back-end), then convert to polars
    import pandas as pd
    raw_sheets: dict[str, "pd.DataFrame"] = pd.read_excel(
        fp, sheet_name=None
    )

    sheet_profiles: dict[str, list[dict]] = {}
    for sheet_name, pdf in raw_sheets.items():
        df = pl.from_pandas(pdf)
        sheet_profiles[sheet_name] = profile_sheet(df)
        print(f"  ✓ {sheet_name}  ({len(df):,} rows × {len(df.columns)} cols)")

    html = render_html(fp.name, sheet_profiles)

    out_path = fp.with_suffix("").name + "_profile.html"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_path


def main():
    files = sys.argv[1:] or ["Oracle.xlsx", "SQLServer.xlsx"]
    for path in files:
        print(f"\nProfiling: {path}")
        out = profile_file(path)
        print(f"  → Report saved to: {out}")


if __name__ == "__main__":
    main()
