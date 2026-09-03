"""Detailed source/target status report + conversion-effort report (Markdown)."""
from __future__ import annotations

import os
from typing import List, Sequence

from ..analyzer import AnalysisResult


def _md_table(headers: Sequence[str], rows: List[Sequence]) -> str:
    out = ["| " + " | ".join(str(h) for h in headers) + " |"]
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def write_reports(analysis: AnalysisResult, out_dir: str, generated_at: str = "") -> dict:
    os.makedirs(out_dir, exist_ok=True)
    status_path = os.path.join(out_dir, "MIGRATION_STATUS_REPORT.md")
    effort_path = os.path.join(out_dir, "CONVERSION_EFFORT_REPORT.md")

    with open(status_path, "w", encoding="utf-8") as fh:
        fh.write(_status_report(analysis, generated_at))
    with open(effort_path, "w", encoding="utf-8") as fh:
        fh.write(_effort_report(analysis, generated_at))
    return {"status": status_path, "effort": effort_path}


def _status_report(a: AnalysisResult, generated_at: str) -> str:
    schema = a.schema
    counts = schema.object_counts()
    sc = a.status_counts()

    lines = [
        f"# Database Migration Status Report",
        "",
        f"- **Source engine:** {a.source_engine}",
        f"- **Target engine:** {a.target_engine}",
        f"- **Source schema:** {schema.name}",
    ]
    if generated_at:
        lines.append(f"- **Generated:** {generated_at}")
    lines += [
        f"- **Average compatibility:** {a.avg_compatibility()}%",
        "",
        "## 1. Object Inventory (Source → Target)",
        "",
        _md_table(["Object Type", "Source Count", "Convertible (Auto+Review)", "Manual"],
                  _inventory_rows(a, counts)),
        "",
        "## 2. Object-by-Object Status",
        "",
        _md_table(
            ["Type", "Name", "Compatibility %", "Target State", "Risk", "Effort (h)", "Detail"],
            [[o.object_type, o.name, o.compatibility, o.status, o.risk, o.effort_hours, o.detail]
             for o in a.objects]),
        "",
        "### Target-state legend",
        "- **Automatic** (≥90%): can be generated & applied with minimal review.",
        "- **Review** (60–89%): generated, but verify datatypes/semantics.",
        "- **Manual** (<60%): requires hand conversion (typically procedural code).",
        "",
        "## 3. Column Datatype Mapping",
        "",
        _md_table(
            ["Table", "Column", "Source Type", "Target Type", "Compat %", "Note"],
            [[c.table, c.column, c.source_type, c.target_type, c.compatibility, c.note]
             for c in a.column_mappings]),
        "",
        "## 4. Summary",
        "",
        _md_table(["Metric", "Value"], [
            ["Total objects", len(a.objects)],
            ["Automatic", sc.get("Automatic", 0)],
            ["Review", sc.get("Review", 0)],
            ["Manual", sc.get("Manual", 0)],
            ["Average compatibility", f"{a.avg_compatibility()}%"],
            ["Total effort", f"{a.total_effort()} h ({round(a.total_effort()/8.0,1)} person-days)"],
        ]),
        "",
    ]
    return "\n".join(lines) + "\n"


def _inventory_rows(a: AnalysisResult, counts) -> list:
    rows = []
    type_key = {
        "tables": "table", "views": "view", "procedures": "procedure",
        "functions": "function", "triggers": "trigger", "sequences": "sequence",
    }
    for label, key in type_key.items():
        objs = [o for o in a.objects if o.object_type == key]
        manual = sum(1 for o in objs if o.status == "Manual")
        conv = len(objs) - manual
        rows.append([label.capitalize(), counts.get(label, 0), conv, manual])
    return rows


def _effort_report(a: AnalysisResult, generated_at: str) -> str:
    by_type = a.effort_by_type()
    total = a.total_effort()
    days = round(total / 8.0, 1)

    # Bucket objects by risk for the effort narrative.
    buckets = {"Low": [], "Medium": [], "High": [], "Very High": []}
    for o in a.objects:
        buckets.setdefault(o.risk, []).append(o)

    lines = [
        "# Conversion Effort Report",
        "",
        f"- **Source → Target:** {a.source_engine} → {a.target_engine}",
    ]
    if generated_at:
        lines.append(f"- **Generated:** {generated_at}")
    lines += [
        f"- **Estimated total effort:** **{total} hours (~{days} person-days)**",
        "",
        "## Effort by Object Type",
        "",
        _md_table(["Object Type", "Effort (hours)", "Effort (person-days)"],
                  [[k, v, round(v / 8.0, 1)] for k, v in by_type.items()]
                  + [["TOTAL", total, days]]),
        "",
        "## Effort by Risk Band",
        "",
        _md_table(["Risk", "# Objects", "Effort (hours)"],
                  [[r, len(objs), round(sum(o.effort_hours for o in objs), 2)]
                   for r, objs in buckets.items() if objs]),
        "",
        "## Effort Model (how these numbers are derived)",
        "",
        "Per-object hours = `base_hours[type] × (1 + (100 − compatibility)/100 × 3)`",
        "plus a small factor for table constraints. Base hours:",
        "",
        _md_table(["Object Type", "Base Hours"],
                  [["table", 1.0], ["view", 1.5], ["procedure", 4.0],
                   ["function", 3.0], ["trigger", 2.5], ["sequence", 0.25]]),
        "",
        "> These are planning estimates. Actuals depend on business-logic",
        "> complexity, test coverage and data-migration/validation scope,",
        "> which are not captured by static schema analysis.",
        "",
        "## Recommended Sequencing",
        "",
        "1. **Sequences & tables** (mostly Automatic) — establish the schema.",
        "2. **Views** (Review) — validate vendor function usage.",
        "3. **Functions/Procedures** (Manual) — rewrite procedural logic, unit test.",
        "4. **Triggers** (Manual) — reimplement and verify firing semantics.",
        "5. **Data migration & reconciliation** (scope separately).",
        "",
    ]
    return "\n".join(lines) + "\n"
