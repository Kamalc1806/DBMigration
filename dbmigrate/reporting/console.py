"""Plain-text tabular rendering for the console (no dependencies)."""
from __future__ import annotations

from typing import List, Sequence

from ..analyzer import AnalysisResult


def _table(headers: Sequence[str], rows: List[Sequence]) -> str:
    cols = len(headers)
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], len(str(row[i])))

    def fmt(row):
        return " | ".join(str(row[i]).ljust(widths[i]) for i in range(cols))

    sep = "-+-".join("-" * w for w in widths)
    out = [fmt(headers), sep]
    out.extend(fmt(r) for r in rows)
    return "\n".join(out)


def render_console(analysis: AnalysisResult) -> str:
    schema = analysis.schema
    counts = schema.object_counts()
    parts = []

    parts.append(f"SOURCE : {analysis.source_engine}  ({schema.name})")
    parts.append(f"TARGET : {analysis.target_engine}")
    parts.append("")
    parts.append("OBJECT INVENTORY")
    inv_rows = [[k.capitalize(), v] for k, v in counts.items()]
    parts.append(_table(["Object Type", "Count"], inv_rows))
    parts.append("")

    parts.append("OBJECT MAPPING & COMPATIBILITY")
    obj_rows = []
    for o in analysis.objects:
        obj_rows.append([
            o.object_type, o.name, f"{o.compatibility}%", o.status, o.risk,
            f"{o.effort_hours}h", o.detail,
        ])
    parts.append(_table(
        ["Type", "Name", "Compat", "Status", "Risk", "Effort", "Detail"], obj_rows))
    parts.append("")

    parts.append("COLUMN DATATYPE MAPPING (sample up to 40 rows)")
    col_rows = []
    for cm in analysis.column_mappings[:40]:
        col_rows.append([
            cm.table, cm.column, cm.source_type, cm.target_type,
            f"{cm.compatibility}%",
        ])
    if col_rows:
        parts.append(_table(
            ["Table", "Column", "Source Type", "Target Type", "Compat"], col_rows))
        if len(analysis.column_mappings) > 40:
            parts.append(f"... {len(analysis.column_mappings) - 40} more columns "
                         f"(see Excel workbook).")
    parts.append("")

    sc = analysis.status_counts()
    parts.append("SUMMARY")
    parts.append(_table(
        ["Metric", "Value"],
        [
            ["Objects total", len(analysis.objects)],
            ["Avg compatibility", f"{analysis.avg_compatibility()}%"],
            ["Automatic", sc.get("Automatic", 0)],
            ["Review", sc.get("Review", 0)],
            ["Manual", sc.get("Manual", 0)],
            ["Total effort (hours)", analysis.total_effort()],
            ["Total effort (person-days)", round(analysis.total_effort() / 8.0, 1)],
        ],
    ))
    return "\n".join(parts)
