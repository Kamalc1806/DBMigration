"""Offline DDL parser.

A pragmatic, dependency-free parser for CREATE statements in a .sql dump. It
handles the object kinds this plugin cares about (tables, views, procedures,
functions, triggers, sequences) well enough to drive analysis, mapping and
target-script generation. It is intentionally forgiving rather than a full SQL
grammar.
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..model import (Column, Constraint, Routine, Schema, Sequence, Table,
                     Trigger, View)
from .base import SchemaConnector

# Multiword base types that must be detected before falling back to first-word.
_MULTIWORD_TYPES = [
    "TIMESTAMP WITH LOCAL TIME ZONE",
    "TIMESTAMP WITH TIME ZONE",
    "INTERVAL YEAR TO MONTH",
    "INTERVAL DAY TO SECOND",
    "DOUBLE PRECISION",
    "LONG RAW",
    "BINARY_DOUBLE",
    "BINARY_FLOAT",
    "CHARACTER VARYING",
]

_COLUMN_STOP_KEYWORDS = {
    "NOT", "NULL", "DEFAULT", "PRIMARY", "UNIQUE", "REFERENCES",
    "CHECK", "GENERATED", "CONSTRAINT", "COLLATE", "ENABLE", "AUTO_INCREMENT",
}


class DDLFileConnector(SchemaConnector):
    def __init__(self, path: str, engine: str):
        self.path = path
        self.engine = engine

    def extract(self) -> Schema:
        with open(self.path, "r", encoding="utf-8") as fh:
            text = fh.read()
        return parse_ddl(text, self.engine, name=self.path)


# --------------------------------------------------------------------------- #
# Statement splitting
# --------------------------------------------------------------------------- #
def _strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


_PROCEDURAL_CREATE = re.compile(
    r"\bCREATE\b(?:\s+OR\s+REPLACE)?\s+(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b",
    re.I)


def _split_statements(sql: str) -> List[str]:
    sql = _strip_comments(sql)
    # First break on batch terminators: a lone "/" (Oracle) or "GO" (T-SQL).
    chunks, buf = [], []
    for line in sql.splitlines():
        st = line.strip()
        if st == "/" or st.upper() == "GO":
            chunks.append("\n".join(buf))
            buf = []
        else:
            buf.append(line)
    if buf:
        chunks.append("\n".join(buf))

    statements: List[str] = []
    for chunk in chunks:
        if chunk.strip():
            statements.extend(_process_chunk(chunk))
    return [s for s in statements if s.strip()]


def _process_chunk(chunk: str) -> List[str]:
    """A batch may hold several ';'-terminated DDL statements followed by at
    most one procedural block (terminated by the batch's '/' or 'GO'). Split
    the plain DDL on ';' and treat the procedural tail as one statement."""
    m = _PROCEDURAL_CREATE.search(chunk)
    if m:
        pre, proc = chunk[:m.start()], chunk[m.start():].strip()
        stmts = _split_on_semicolons(pre)
        if proc:
            stmts.append(proc)
        return stmts
    return _split_on_semicolons(chunk)


def _split_on_semicolons(chunk: str) -> List[str]:
    """Split on ';' while ignoring semicolons inside string literals."""
    out, cur, in_str = [], [], False
    for ch in chunk:
        if ch == "'":
            in_str = not in_str
            cur.append(ch)
        elif ch == ";" and not in_str:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return [s for s in out if s.strip()]


# --------------------------------------------------------------------------- #
# Top-level parse
# --------------------------------------------------------------------------- #
def parse_ddl(text: str, engine: str, name: str = "source") -> Schema:
    schema = Schema(engine=engine, name=name)
    for stmt in _split_statements(text):
        head = stmt.lstrip()
        if re.match(r"CREATE\s+TABLE", head, re.I):
            tbl = _parse_table(stmt)
            if tbl:
                schema.tables.append(tbl)
        elif re.match(r"CREATE(\s+OR\s+REPLACE)?\s+VIEW", head, re.I):
            v = _parse_view(stmt)
            if v:
                schema.views.append(v)
        elif re.match(r"CREATE(\s+OR\s+REPLACE)?\s+PROCEDURE", head, re.I):
            schema.routines.append(_parse_routine(stmt, "PROCEDURE", engine))
        elif re.match(r"CREATE(\s+OR\s+REPLACE)?\s+FUNCTION", head, re.I):
            schema.routines.append(_parse_routine(stmt, "FUNCTION", engine))
        elif re.match(r"CREATE(\s+OR\s+REPLACE)?\s+TRIGGER", head, re.I):
            schema.triggers.append(_parse_trigger(stmt))
        elif re.match(r"CREATE\s+SEQUENCE", head, re.I):
            schema.sequences.append(_parse_sequence(stmt))
    return schema


def _clean_ident(ident: str) -> str:
    return ident.strip().strip('"').strip("`").strip("[]").split(".")[-1]


# --------------------------------------------------------------------------- #
# TABLE
# --------------------------------------------------------------------------- #
def _parse_table(stmt: str) -> Optional[Table]:
    m = re.match(r"CREATE\s+TABLE\s+([^\s(]+)\s*\((.*)\)[^)]*$",
                 stmt, re.I | re.S)
    if not m:
        # tolerate trailing storage clauses with unbalanced tail
        m = re.match(r"CREATE\s+TABLE\s+([^\s(]+)\s*\((.*)\)", stmt, re.I | re.S)
        if not m:
            return None
    name = _clean_ident(m.group(1))
    body = m.group(2)
    table = Table(name=name)
    for item in _split_top_level_commas(body):
        item = item.strip()
        if not item:
            continue
        if _looks_like_constraint(item):
            con = _parse_constraint(item)
            if con:
                table.constraints.append(con)
                if con.kind == "PRIMARY KEY":
                    for c in table.columns:
                        if c.name in con.columns:
                            c.nullable = False
        else:
            col = _parse_column(item)
            if col:
                table.columns.append(col)
    return table


def _split_top_level_commas(body: str) -> List[str]:
    out, cur, depth, in_str = [], [], 0, False
    for ch in body:
        if ch == "'":
            in_str = not in_str
        if not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                out.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    if "".join(cur).strip():
        out.append("".join(cur))
    return out


def _looks_like_constraint(item: str) -> bool:
    return bool(re.match(
        r"(CONSTRAINT\b|PRIMARY\s+KEY\b|FOREIGN\s+KEY\b|UNIQUE\b|CHECK\b|KEY\b|INDEX\b)",
        item.strip(), re.I))


def _parse_constraint(item: str) -> Optional[Constraint]:
    item = item.strip()
    name = ""
    m = re.match(r"CONSTRAINT\s+([^\s(]+)\s+(.*)", item, re.I | re.S)
    if m:
        name = _clean_ident(m.group(1))
        item = m.group(2).strip()

    if re.match(r"PRIMARY\s+KEY", item, re.I):
        cols = _cols_in_parens(item)
        return Constraint(name or "pk", "PRIMARY KEY", cols)
    if re.match(r"FOREIGN\s+KEY", item, re.I):
        cols = _cols_in_parens(item)
        return Constraint(name or "fk", "FOREIGN KEY", cols, definition=item)
    if re.match(r"UNIQUE", item, re.I):
        cols = _cols_in_parens(item)
        return Constraint(name or "uq", "UNIQUE", cols)
    if re.match(r"CHECK", item, re.I):
        return Constraint(name or "ck", "CHECK", [], definition=item)
    return None


def _cols_in_parens(text: str) -> List[str]:
    m = re.search(r"\(([^)]*)\)", text)
    if not m:
        return []
    return [_clean_ident(c) for c in m.group(1).split(",") if c.strip()]


def _parse_column(item: str) -> Optional[Column]:
    m = re.match(r'^\s*("?[`\[\]\w$#]+"?)\s+(.*)$', item, re.S)
    if not m:
        return None
    col_name = _clean_ident(m.group(1))
    rest = m.group(2).strip()

    base_type, length, precision, scale, after = _parse_type(rest)
    if not base_type:
        return None
    raw_type = base_type
    if precision is not None and scale is not None:
        raw_type = f"{base_type}({precision},{scale})"
    elif precision is not None:
        raw_type = f"{base_type}({precision})"
    elif length is not None:
        raw_type = f"{base_type}({length})"

    nullable = not re.search(r"\bNOT\s+NULL\b", after, re.I)
    default = None
    dm = re.search(r"\bDEFAULT\s+(.+?)(?:\s+(?:NOT\s+NULL|NULL|ENABLE|CHECK|REFERENCES|PRIMARY|UNIQUE)\b|$)",
                   after, re.I | re.S)
    if dm:
        default = dm.group(1).strip()

    return Column(
        name=col_name, raw_type=raw_type, base_type=base_type,
        length=length, precision=precision, scale=scale,
        nullable=nullable, default=default,
    )


def _parse_type(rest: str):
    """Return (base_type, length, precision, scale, remainder_after_type)."""
    upper = rest.upper()
    base = None
    consumed = 0
    for mw in _MULTIWORD_TYPES:
        if upper.startswith(mw):
            base = mw
            consumed = len(mw)
            break
    if base is None:
        m = re.match(r"([A-Za-z][A-Za-z0-9_]*)", rest)
        if not m:
            return None, None, None, None, rest
        base = m.group(1).upper()
        consumed = m.end()

    remainder = rest[consumed:].lstrip()
    length = precision = scale = None
    numeric = base.upper() in {"NUMBER", "NUMERIC", "DECIMAL", "DEC", "FLOAT"}
    pm = re.match(r"\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)", remainder)
    if pm:
        if pm.group(2) is not None:
            precision = int(pm.group(1))
            scale = int(pm.group(2))
        elif numeric:
            # single arg on a numeric type is precision, not length
            precision = int(pm.group(1))
        else:
            length = int(pm.group(1))
        remainder = remainder[pm.end():].lstrip()
    else:
        # e.g. NUMBER, VARCHAR2(50 CHAR), TIMESTAMP(6)
        pm2 = re.match(r"\(\s*(\d+)\s*\w+\s*\)", remainder)  # (50 CHAR)
        if pm2:
            length = int(pm2.group(1))
            remainder = remainder[pm2.end():].lstrip()
    return base, length, precision, scale, remainder


# --------------------------------------------------------------------------- #
# VIEW / ROUTINE / TRIGGER / SEQUENCE
# --------------------------------------------------------------------------- #
def _parse_view(stmt: str) -> Optional[View]:
    m = re.match(r"CREATE(?:\s+OR\s+REPLACE)?\s+VIEW\s+([^\s(]+).*?\bAS\b(.*)",
                 stmt, re.I | re.S)
    if not m:
        return None
    return View(name=_clean_ident(m.group(1)), definition=m.group(2).strip())


def _parse_routine(stmt: str, kind: str, engine: str) -> Routine:
    m = re.match(rf"CREATE(?:\s+OR\s+REPLACE)?\s+{kind}\s+([^\s(]+)", stmt, re.I)
    name = _clean_ident(m.group(1)) if m else f"unnamed_{kind.lower()}"
    lang = "PL/SQL" if engine == "oracle" else (
        "T-SQL" if engine == "sqlserver" else "SQL")
    return Routine(name=name, kind=kind, definition=stmt.strip(), language=lang)


def _parse_trigger(stmt: str) -> Trigger:
    m = re.match(r"CREATE(?:\s+OR\s+REPLACE)?\s+TRIGGER\s+([^\s(]+)", stmt, re.I)
    name = _clean_ident(m.group(1)) if m else "unnamed_trigger"
    tm = re.search(r"\bON\s+([^\s(]+)", stmt, re.I)
    table = _clean_ident(tm.group(1)) if tm else None
    return Trigger(name=name, table=table, definition=stmt.strip())


def _parse_sequence(stmt: str) -> Sequence:
    m = re.match(r"CREATE\s+SEQUENCE\s+([^\s;]+)", stmt, re.I)
    name = _clean_ident(m.group(1)) if m else "unnamed_seq"
    start = incr = None
    sm = re.search(r"START\s+WITH\s+(\d+)", stmt, re.I)
    if sm:
        start = int(sm.group(1))
    im = re.search(r"INCREMENT\s+BY\s+(\d+)", stmt, re.I)
    if im:
        incr = int(im.group(1))
    return Sequence(name=name, start=start, increment=incr)
