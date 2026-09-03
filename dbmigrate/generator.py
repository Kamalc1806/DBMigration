"""Generate the target-scripts folder tree.

Layout produced under <output>/<target_engine>/:
    tables/       one CREATE TABLE .sql per table (converted datatypes)
    views/        one .sql per view (definition + review header)
    procedures/   one .sql per procedure (original body + review header)
    functions/    one .sql per function
    triggers/     one .sql per trigger
    sequences/    one .sql per sequence
    00_run_all.sql  master script that sources the pieces in order

Table DDL is converted using the datatype mapping. Procedural objects are
emitted with the original body wrapped in a clearly-marked review banner,
because cross-dialect procedural conversion is not safe to do blindly.
"""
from __future__ import annotations

import os
import re
from typing import List

from .analyzer import AnalysisResult
from .mapping import map_datatype
from .mapping.registry import normalize_engine
from .model import Routine, Schema, Table, Trigger
from .translation import get_translator

_TYPE_DIRS = {
    "table": "tables",
    "view": "views",
    "procedure": "procedures",
    "function": "functions",
    "trigger": "triggers",
    "sequence": "sequences",
}


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name)


def _banner(lines: List[str]) -> str:
    width = max(len(x) for x in lines) + 4
    top = "-- " + "=" * width
    body = "\n".join(f"-- {x}" for x in lines)
    return f"{top}\n{body}\n{top}\n"


class TargetGenerator:
    def __init__(self, schema: Schema, analysis: AnalysisResult, output_dir: str):
        self.schema = schema
        self.analysis = analysis
        self.target_engine = normalize_engine(analysis.target_engine)
        self.root = os.path.join(output_dir, self.target_engine)
        self.translator = get_translator(analysis.source_engine, analysis.target_engine)

    def generate(self) -> dict:
        os.makedirs(self.root, exist_ok=True)
        written = {k: [] for k in _TYPE_DIRS}
        for sub in _TYPE_DIRS.values():
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)

        for table in self.schema.tables:
            path = self._write("table", table.name, self._convert_table(table))
            written["table"].append(path)
        for v in self.schema.views:
            written["view"].append(self._write("view", v.name, self._render_view(v)))
        for r in self.schema.routines:
            key = r.kind.lower()
            written[key].append(self._write(key, r.name, self._render_routine(r)))
        for tr in self.schema.triggers:
            written["trigger"].append(self._write("trigger", tr.name, self._render_trigger(tr)))
        for s in self.schema.sequences:
            body = self._convert_sequence(s)
            written["sequence"].append(self._write("sequence", s.name, body))

        master = self._write_master(written)
        return {"root": self.root, "written": written, "master": master}

    # ------------------------------------------------------------------ #
    def _render_view(self, v) -> str:
        banner = _banner([
            f"VIEW: {v.name}",
            "Auto-copied from source. Vendor-specific functions/joins may",
            f"need adjustment for {self.target_engine}.",
        ])
        defn = v.definition.strip().rstrip(";")
        # Some connectors return just the SELECT body, others the full DDL.
        if re.match(r"CREATE\s+(OR\s+REPLACE\s+)?VIEW", defn, re.I):
            stmt = defn
        else:
            stmt = f"CREATE VIEW {v.name} AS\n{defn}"
        return banner + stmt + ";\n"

    def _render_routine(self, r: Routine) -> str:
        if self.translator:
            return self._render_translation(
                r.kind, r.name, self.translator.routine(r),
                extra=f"source language: {r.language}")
        return _banner([
            f"{r.kind}: {r.name}  (source language: {r.language})",
            "MANUAL REVIEW REQUIRED: procedural code does not convert 1:1.",
            f"Rewrite the body below in {self.target_engine}'s procedural language.",
        ]) + r.definition.rstrip() + "\n"

    def _render_trigger(self, tr: Trigger) -> str:
        if self.translator:
            return self._render_translation(
                "TRIGGER", tr.name, self.translator.trigger(tr),
                extra=f"on {tr.table}")
        return _banner([
            f"TRIGGER: {tr.name} on {tr.table}",
            "MANUAL REVIEW REQUIRED: trigger semantics/syntax differ by engine.",
        ]) + tr.definition.rstrip() + "\n"

    def _render_translation(self, kind: str, name: str, res, extra: str = "") -> str:
        """Emit auto-translated code + confidence + notes, keeping the original
        source as a commented reference block."""
        head = [f"{kind}: {name}   ({self.analysis.source_engine} -> {self.target_engine})"]
        if extra:
            head.append(extra)
        head.append(f"AUTO-TRANSLATED  |  confidence: {res.confidence}%  |  REVIEW REQUIRED")
        if res.notes:
            head.append("Translation notes:")
            head.extend("  - " + n for n in res.notes)
        banner = _banner(head)
        original = "\n".join("-- | " + ln for ln in res.original.rstrip().splitlines())
        ref = ("\n-- " + "-" * 70 +
               "\n-- ORIGINAL SOURCE (reference; delete once verified):\n" +
               original + "\n-- " + "-" * 70 + "\n")
        return banner + res.code.rstrip() + "\n" + ref

    def _write(self, object_type: str, name: str, content: str) -> str:
        sub = _TYPE_DIRS[object_type]
        path = os.path.join(self.root, sub, f"{_safe(name)}.sql")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def _convert_table(self, table: Table) -> str:
        src = self.analysis.source_engine
        lines = [f"CREATE TABLE {table.name} ("]
        col_lines = []
        low_compat_notes = []
        for col in table.columns:
            tm = map_datatype(src, self.target_engine, col)
            null_sql = "" if col.nullable else " NOT NULL"
            default_sql = f" DEFAULT {col.default}" if col.default else ""
            col_lines.append(f"    {col.name} {tm.target_type}{null_sql}{default_sql}")
            if tm.compatibility < 80:
                low_compat_notes.append(
                    f"{col.name}: {tm.source_type} -> {tm.target_type} "
                    f"({tm.compatibility}%) {tm.note}")

        # inline constraints
        for con in table.constraints:
            if con.kind == "PRIMARY KEY" and con.columns:
                col_lines.append(f"    CONSTRAINT {con.name} PRIMARY KEY ({', '.join(con.columns)})")
            elif con.kind == "UNIQUE" and con.columns:
                col_lines.append(f"    CONSTRAINT {con.name} UNIQUE ({', '.join(con.columns)})")
            elif con.kind == "FOREIGN KEY" and con.definition:
                d = con.definition.strip()
                if not re.match(r"FOREIGN\s+KEY", d, re.I):
                    cols = ", ".join(con.columns)
                    d = f"FOREIGN KEY ({cols}) {d}"
                col_lines.append(f"    CONSTRAINT {con.name} {d}")
            elif con.kind == "CHECK" and con.definition:
                col_lines.append(f"    CONSTRAINT {con.name} {con.definition}")

        lines.append(",\n".join(col_lines))
        lines.append(");")
        body = "\n".join(lines) + "\n"

        header_lines = [f"TABLE: {table.name}   ({src} -> {self.target_engine})"]
        if low_compat_notes:
            header_lines.append("Columns needing review:")
            header_lines.extend("  - " + n for n in low_compat_notes)
        else:
            header_lines.append("All columns mapped with high compatibility.")
        return _banner(header_lines) + body

    def _convert_sequence(self, seq) -> str:
        start = seq.start if seq.start is not None else 1
        incr = seq.increment if seq.increment is not None else 1
        if self.target_engine == "postgresql":
            return (f"CREATE SEQUENCE {seq.name} START WITH {start} INCREMENT BY {incr};\n")
        if self.target_engine == "oracle":
            return (f"CREATE SEQUENCE {seq.name} START WITH {start} INCREMENT BY {incr} NOCACHE;\n")
        # mysql has no sequences -> emulate note
        return _banner([
            f"SEQUENCE: {seq.name}",
            f"{self.target_engine} may not support native sequences; "
            "use AUTO_INCREMENT or a sequence table.",
        ]) + f"-- START WITH {start} INCREMENT BY {incr}\n"

    def _write_master(self, written: dict) -> str:
        order = ["sequences", "tables", "views", "functions", "procedures", "triggers"]
        lines = [
            "-- Master run script (generated).",
            f"-- Target engine: {self.target_engine}",
            "-- Run objects in dependency-friendly order.\n",
        ]
        rev = {v: k for k, v in _TYPE_DIRS.items()}
        for sub in order:
            otype = rev[sub]
            files = written.get(otype, [])
            if not files:
                continue
            lines.append(f"\n-- ---- {sub} ----")
            for path in files:
                rel = os.path.join(sub, os.path.basename(path)).replace("\\", "/")
                lines.append(f"\\i {rel}" if self.target_engine == "postgresql" else f"-- @{rel}")
        path = os.path.join(self.root, "00_run_all.sql")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return path
