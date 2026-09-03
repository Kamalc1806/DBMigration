"""Oracle PL/SQL  ->  PostgreSQL PL/pgSQL translator (best-effort).

Handles the common shapes of functions, procedures and row triggers:
  * header + parameter list (IN/OUT/IN OUT -> PG modes, datatype mapping)
  * RETURN type (functions)
  * DECLARE section (variable datatype mapping)
  * body token rewrites (NVL->COALESCE, SYSDATE->CURRENT_TIMESTAMP,
    seq.NEXTVAL->nextval('seq'), DUAL removal, DBMS_OUTPUT->RAISE NOTICE, ...)
  * triggers -> trigger function + CREATE TRIGGER ... EXECUTE FUNCTION

Anything risky (cursors, %TYPE, exceptions, ROWNUM, bulk ops, ...) is left in
place but flagged in the result notes and lowers the confidence score.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from ..connectors.ddl_file import _split_top_level_commas
from ..model import Routine, Trigger
from .base import TranslationResult
from .typeutil import map_type_string

SRC, TGT = "oracle", "postgresql"

# (regex, replacement, note) - simple, safe token rewrites applied to a body.
_BODY_REWRITES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(r"\bNVL\s*\(", re.I), "COALESCE(", ""),
    (re.compile(r"\bNVL2\s*\(", re.I), "COALESCE(", "NVL2 partially mapped to COALESCE - verify arity."),
    (re.compile(r"\bSYSTIMESTAMP\b", re.I), "CURRENT_TIMESTAMP", ""),
    (re.compile(r"\bSYSDATE\b", re.I), "CURRENT_TIMESTAMP", ""),
    (re.compile(r"\bFROM\s+DUAL\b", re.I), "", "Removed FROM DUAL (not needed in PostgreSQL)."),
    (re.compile(r"(\w+)\.NEXTVAL\b", re.I), r"nextval('\1')", ""),
    (re.compile(r"(\w+)\.CURRVAL\b", re.I), r"currval('\1')", ""),
    (re.compile(r"\bSUBSTR\s*\(", re.I), "SUBSTRING(", "SUBSTR->SUBSTRING: verify argument semantics."),
]

# Constructs we do NOT auto-translate; flag + penalize confidence.
_RISK_FLAGS: List[Tuple[re.Pattern, int, str]] = [
    (re.compile(r"%TYPE\b|%ROWTYPE\b", re.I), 10,
     "Anchored types (%TYPE/%ROWTYPE) used - supported by PG but verify."),
    (re.compile(r"\bCURSOR\b", re.I), 10, "Explicit cursor(s) - verify PL/pgSQL cursor syntax."),
    (re.compile(r"\bEXCEPTION\b", re.I), 12,
     "EXCEPTION handler - Oracle exception names/SQLCODE differ from PG."),
    (re.compile(r"\bROWNUM\b", re.I), 12,
     "ROWNUM has no PG equivalent - rewrite with LIMIT / ROW_NUMBER()."),
    (re.compile(r"\bBULK\s+COLLECT\b|\bFORALL\b", re.I), 15,
     "Bulk operations (BULK COLLECT/FORALL) need manual rewrite."),
    (re.compile(r"\bCONNECT\s+BY\b", re.I), 15,
     "CONNECT BY hierarchical query - rewrite as recursive CTE."),
    (re.compile(r"\bDBMS_(?!OUTPUT)\w+", re.I), 12,
     "DBMS_* package call(s) - no PG equivalent; rewrite required."),
    (re.compile(r"\bPRAGMA\b", re.I), 5, "PRAGMA directive(s) ignored in PG."),
    (re.compile(r"\bMERGE\b", re.I), 8, "MERGE - use INSERT ... ON CONFLICT in PG."),
]


def _indent_body(body: str) -> str:
    return "\n".join(("    " + ln if ln.strip() else ln)
                     for ln in body.strip().splitlines())


def _apply_body_rewrites(body: str, notes: List[str]) -> str:
    # DBMS_OUTPUT.PUT_LINE(x); -> RAISE NOTICE '%', x;
    body, n = re.subn(r"DBMS_OUTPUT\.PUT_LINE\s*\((.*?)\)\s*;",
                      r"RAISE NOTICE '%', \1;", body, flags=re.I | re.S)
    if n:
        notes.append("DBMS_OUTPUT.PUT_LINE -> RAISE NOTICE.")
    # COMMIT/ROLLBACK cannot appear in functions and behave differently in procs.
    body, n = re.subn(r"\b(COMMIT|ROLLBACK)\s*;",
                      r"-- \1;  -- (transaction control removed - review)", body, flags=re.I)
    if n:
        notes.append("COMMIT/ROLLBACK commented out (not allowed in functions; "
                     "review for procedures).")
    for pat, repl, note in _BODY_REWRITES:
        body, n = pat.subn(repl, body)
        if n and note:
            notes.append(note)
    return body


def _flag_risks(text: str, notes: List[str]) -> int:
    penalty = 0
    for pat, pen, note in _RISK_FLAGS:
        if pat.search(text):
            penalty += pen
            notes.append(note)
    return penalty


def _extract_balanced(text: str, open_idx: int) -> Tuple[str, int]:
    """Given index of '(', return (inner_text, index_after_matching_paren)."""
    depth, i = 0, open_idx
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i], i + 1
        i += 1
    return text[open_idx + 1:], len(text)


def _translate_params(params_str: str, notes: List[str]) -> str:
    out = []
    for raw in _split_top_level_commas(params_str):
        p = raw.strip()
        if not p:
            continue
        m = re.match(r"([\w$#]+)\s+(IN\s+OUT|IN|OUT)?\s*(.*)", p, re.I | re.S)
        if not m:
            out.append(p)
            continue
        name = m.group(1)
        mode = re.sub(r"\s+", " ", (m.group(2) or "").strip().upper())
        rest = m.group(3).strip()
        default = None
        dm = re.split(r"\s*(?::=|DEFAULT)\s*", rest, maxsplit=1, flags=re.I)
        type_str = dm[0].strip()
        if len(dm) > 1:
            default = dm[1].strip()
        tgt_type = map_type_string(SRC, TGT, type_str)
        pg_mode = {"IN": "", "OUT": "OUT ", "IN OUT": "INOUT ", "": ""}.get(mode, "")
        piece = f"{pg_mode}{name} {tgt_type}"
        if default:
            piece += f" DEFAULT {default}"
        out.append(piece)
    return ", ".join(out)


def _translate_declarations(decls: str, notes: List[str]) -> str:
    lines = []
    for stmt in decls.split(";"):
        s = stmt.strip()
        if not s:
            continue
        m = re.match(r"([\w$#]+)\s+(.*)", s, re.S)
        if not m:
            lines.append(f"    {s};")
            continue
        name, rest = m.group(1), m.group(2).strip()
        # split off a := / DEFAULT initializer
        dm = re.split(r"\s*(?::=|DEFAULT)\s*", rest, maxsplit=1, flags=re.I)
        type_str = dm[0].strip()
        init = dm[1].strip() if len(dm) > 1 else None
        if "%TYPE" in type_str.upper() or "%ROWTYPE" in type_str.upper():
            decl = f"    {name} {type_str}"          # keep anchored type as-is
        else:
            decl = f"    {name} {map_type_string(SRC, TGT, type_str)}"
        if init:
            decl += f" := {init}"
        lines.append(decl + ";")
    return "\n".join(lines)


def _split_header_body(defn: str):
    """Return (header_text, body_text) splitting at the first top-level BEGIN."""
    bm = re.search(r"\bBEGIN\b", defn, re.I)
    if not bm:
        return defn, ""
    header = defn[:bm.start()]
    tail = defn[bm.end():]
    # strip the trailing END [name]; and any '/'
    body = re.sub(r"\bEND\s*[\w$#]*\s*;?\s*/?\s*$", "", tail.strip(), flags=re.I)
    return header, body


def translate_routine(routine: Routine) -> TranslationResult:
    notes: List[str] = []
    defn = routine.definition
    header, body = _split_header_body(defn)

    hm = re.match(r"\s*CREATE\s+(?:OR\s+REPLACE\s+)?(FUNCTION|PROCEDURE)\s+([\w.\"$#]+)",
                  header, re.I)
    if not hm:
        return TranslationResult(defn, 40, False,
                                 ["Could not parse routine header; left unchanged."], defn)
    kind = hm.group(1).upper()
    name = hm.group(2).strip('"')
    after = header[hm.end():].lstrip()

    params_str = ""
    if after.startswith("("):
        params_str, end = _extract_balanced(after, 0)
        after = after[end:].lstrip()

    return_type = None
    if kind == "FUNCTION":
        rm = re.match(r"RETURN\s+([A-Za-z0-9_ ,()]+?)\s+(?:IS|AS)\b", after, re.I)
        if rm:
            return_type = map_type_string(SRC, TGT, rm.group(1).strip())
            decls = after[rm.end():]
        else:
            decls = re.sub(r"^.*?\b(?:IS|AS)\b", "", after, count=1, flags=re.I | re.S)
    else:
        decls = re.sub(r"^\s*(?:IS|AS)\b", "", after, count=1, flags=re.I | re.S)

    pg_params = _translate_params(params_str, notes)
    pg_decls = _translate_declarations(decls, notes)
    penalty = _flag_risks(decls + "\n" + body, notes)
    pg_body = _apply_body_rewrites(body, notes)

    declare_block = f"DECLARE\n{pg_decls}\n" if pg_decls.strip() else ""
    if kind == "FUNCTION":
        head = (f"CREATE OR REPLACE FUNCTION {name}({pg_params})\n"
                f"RETURNS {return_type or 'void'} AS $$\n")
        tail = "$$ LANGUAGE plpgsql;\n"
    else:
        head = f"CREATE OR REPLACE PROCEDURE {name}({pg_params})\nLANGUAGE plpgsql AS $$\n"
        tail = "$$;\n"

    code = f"{head}{declare_block}BEGIN\n{_indent_body(pg_body)}\nEND;\n{tail}"
    confidence = max(35, 80 - penalty)
    return TranslationResult(code=code, confidence=confidence, translated=True,
                             notes=notes, original=defn)


_TRIGGER_TIMING = re.compile(r"\b(BEFORE|AFTER|INSTEAD\s+OF)\b", re.I)


def translate_trigger(trig: Trigger) -> TranslationResult:
    notes: List[str] = []
    defn = trig.definition
    header, body = _split_header_body(defn)

    tm = _TRIGGER_TIMING.search(header)
    timing = re.sub(r"\s+", " ", tm.group(1).upper()) if tm else "AFTER"
    events = [e.upper() for e in re.findall(r"\b(INSERT|UPDATE|DELETE)\b",
                                            header[tm.end():] if tm else header, re.I)]
    events = list(dict.fromkeys(events)) or ["INSERT"]
    table = trig.table or "??"
    for_each_row = bool(re.search(r"FOR\s+EACH\s+ROW", header, re.I))

    # :NEW/:OLD -> NEW/OLD, plus generic body rewrites
    body = re.sub(r":NEW\b", "NEW", body, flags=re.I)
    body = re.sub(r":OLD\b", "OLD", body, flags=re.I)
    penalty = _flag_risks(body, notes)
    body = _apply_body_rewrites(body, notes)

    fn_name = f"{trig.name}_fn"
    ret = "NEW" if timing != "AFTER" else "NEW"
    fn = (f"CREATE OR REPLACE FUNCTION {fn_name}()\nRETURNS TRIGGER AS $$\n"
          f"BEGIN\n{_indent_body(body)}\n    RETURN {ret};\nEND;\n$$ LANGUAGE plpgsql;\n\n")
    level = "FOR EACH ROW" if for_each_row else "FOR EACH STATEMENT"
    ddl = (f"CREATE TRIGGER {trig.name}\n{timing} {' OR '.join(events)} ON {table}\n"
           f"{level} EXECUTE FUNCTION {fn_name}();\n")

    notes.append("Trigger split into a trigger-function + CREATE TRIGGER (PG pattern).")
    confidence = max(35, 70 - penalty)
    return TranslationResult(code=fn + ddl, confidence=confidence, translated=True,
                             notes=notes, original=defn)
