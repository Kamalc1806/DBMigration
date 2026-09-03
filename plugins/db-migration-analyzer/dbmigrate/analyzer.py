"""Analyze a source :class:`Schema` against a target engine.

Produces:
  * a flat list of column-level datatype mappings (for the tabular view / Excel)
  * a per-object analysis (compatibility %, effort hours, risk)
  * roll-up summary numbers used by the reports
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .mapping import map_datatype, map_object_compatibility
from .model import Schema


# --- Effort model ---------------------------------------------------------- #
# Base hours per object type + adjustment by compatibility. Transparent and
# tunable; these are planning estimates, not guarantees.
_BASE_HOURS = {
    "table": 1.0,
    "view": 1.5,
    "procedure": 4.0,
    "function": 3.0,
    "trigger": 2.5,
    "sequence": 0.25,
}


def _effort_hours(object_type: str, compatibility: int, extra_factor: float = 1.0) -> float:
    base = _BASE_HOURS.get(object_type, 2.0)
    # lower compatibility -> more hours. 100% -> x1, 0% -> x4.
    multiplier = 1.0 + (100 - compatibility) / 100.0 * 3.0
    return round(base * multiplier * extra_factor, 2)


def _risk(compatibility: int) -> str:
    if compatibility >= 90:
        return "Low"
    if compatibility >= 70:
        return "Medium"
    if compatibility >= 45:
        return "High"
    return "Very High"


@dataclass
class ColumnMapping:
    table: str
    column: str
    source_type: str
    target_type: str
    compatibility: int
    nullable: bool
    note: str


@dataclass
class ObjectAnalysis:
    object_type: str
    name: str
    compatibility: int          # 0-100 (avg for tables, baseline for routines)
    status: str                 # Automatic | Review | Manual
    effort_hours: float
    risk: str
    detail: str = ""


@dataclass
class AnalysisResult:
    source_engine: str
    target_engine: str
    schema: Schema
    column_mappings: List[ColumnMapping] = field(default_factory=list)
    objects: List[ObjectAnalysis] = field(default_factory=list)

    # roll-ups
    def total_effort(self) -> float:
        return round(sum(o.effort_hours for o in self.objects), 2)

    def avg_compatibility(self) -> float:
        if not self.objects:
            return 0.0
        return round(sum(o.compatibility for o in self.objects) / len(self.objects), 1)

    def status_counts(self) -> Dict[str, int]:
        counts = {"Automatic": 0, "Review": 0, "Manual": 0}
        for o in self.objects:
            counts[o.status] = counts.get(o.status, 0) + 1
        return counts

    def effort_by_type(self) -> Dict[str, float]:
        agg: Dict[str, float] = {}
        for o in self.objects:
            agg[o.object_type] = round(agg.get(o.object_type, 0.0) + o.effort_hours, 2)
        return agg


def _status_from_compat(compatibility: int) -> str:
    if compatibility >= 90:
        return "Automatic"
    if compatibility >= 60:
        return "Review"
    return "Manual"


def analyze(schema: Schema, target_engine: str) -> AnalysisResult:
    src = schema.engine
    result = AnalysisResult(source_engine=src, target_engine=target_engine, schema=schema)

    # ---- Tables: map every column, derive table-level compatibility -------- #
    for table in schema.tables:
        compat_scores = []
        for col in table.columns:
            tm = map_datatype(src, target_engine, col)
            compat_scores.append(tm.compatibility)
            result.column_mappings.append(ColumnMapping(
                table=table.name, column=col.name,
                source_type=tm.source_type, target_type=tm.target_type,
                compatibility=tm.compatibility, nullable=col.nullable,
                note=tm.note,
            ))
        avg = int(round(sum(compat_scores) / len(compat_scores))) if compat_scores else 85
        # constraints add a little risk/effort
        extra = 1.0 + 0.1 * len(table.constraints)
        result.objects.append(ObjectAnalysis(
            object_type="table", name=table.name, compatibility=avg,
            status=_status_from_compat(avg), effort_hours=_effort_hours("table", avg, extra),
            risk=_risk(avg),
            detail=f"{len(table.columns)} cols, {len(table.constraints)} constraints, "
                   f"{len(table.indexes)} indexes",
        ))

    # ---- Views & procedural objects: baseline compatibility ---------------- #
    def add_object(object_type: str, name: str, detail: str = ""):
        compat = map_object_compatibility(src, target_engine, object_type)
        result.objects.append(ObjectAnalysis(
            object_type=object_type, name=name, compatibility=compat,
            status=_status_from_compat(compat), effort_hours=_effort_hours(object_type, compat),
            risk=_risk(compat), detail=detail,
        ))

    for v in schema.views:
        add_object("view", v.name, "SQL view (may reference vendor functions)")
    for r in schema.routines:
        add_object(r.kind.lower(), r.name, f"{r.language or ''} body ~"
                                           f"{len(r.definition.splitlines())} lines")
    for tr in schema.triggers:
        add_object("trigger", tr.name, f"on {tr.table or '?'}")
    for s in schema.sequences:
        add_object("sequence", s.name, f"start={s.start}, incr={s.increment}")

    return result
