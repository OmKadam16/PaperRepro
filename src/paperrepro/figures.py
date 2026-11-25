"""Stage 3 server side: parse CSV, describe a figure for the Caption Writer. No plotting here;
the browser draws the chart from the same CSV and spec."""
from __future__ import annotations

import csv
import io
import math

from paperrepro.state import Figure

MAX_CSV = 500_000


def parse(text: str) -> tuple[list[str], list[list[str]]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if not rows:
        return [], []
    head = [h.strip() or f"column {i + 1}" for i, h in enumerate(rows[0])]
    return head, [r + [""] * (len(head) - len(r)) for r in rows[1:]]


def _num(v: str) -> float | None:
    try:
        x = float(v.replace(",", "").strip())
        return x if math.isfinite(x) else None
    except ValueError:
        return None


def describe(fig: Figure) -> str:
    """Facts about the figure, computed from the data, for the Caption Writer."""
    head, rows = parse(fig.csv)
    sp = fig.spec
    col = {h: i for i, h in enumerate(head)}
    lines = [f"chart type: {sp.chart}", f"title (working): {fig.title}",
             f"x axis: {sp.xlabel or sp.x} (column '{sp.x}')", f"y axis: {sp.ylabel or ', '.join(sp.ys)}",
             f"number of data rows: {len(rows)}"]
    if sp.x in col:
        xs = [r[col[sp.x]] for r in rows]
        nums = [v for v in (_num(x) for x in xs) if v is not None]
        lines.append(f"x values: {min(nums):g} to {max(nums):g}" if len(nums) == len(xs) and nums
                     else f"x categories: {', '.join(xs[:12])}{' …' if len(xs) > 12 else ''}")
    for y in sp.ys:
        if y not in col:
            continue
        vals = [v for v in (_num(r[col[y]]) for r in rows) if v is not None]
        if vals:
            lines.append(f"series '{y}': {len(vals)} values, min {min(vals):g}, max {max(vals):g}, "
                         f"first {vals[0]:g}, last {vals[-1]:g}")
        if sp.errors.get(y) in col:
            lines.append(f"series '{y}' has error bars from column '{sp.errors[y]}' (what they represent is not stated)")
    if sp.log_y:
        lines.append("y axis is logarithmic")
    if sp.fit and sp.chart == "scatter":
        lines.append("a least-squares line is drawn")
    return "\n".join(lines)
