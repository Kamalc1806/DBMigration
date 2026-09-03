# dbmigrate — Database Migration Analysis & Scripting Plugin

`dbmigrate` is a Python plugin that takes a **source database** and a **target
database engine**, analyzes the source, maps every object to the target (with a
datatype-level **compatibility percentage**), generates a ready-to-review
**target-scripts folder tree**, and produces **Excel + detailed reports** —
including an **effort estimate** for the conversion.

It is engine-agnostic and extensible: mappings are data-driven, so new
source→target engine pairs are added by editing a table, not the code.

---

## What it does (maps to the original requirements)

| # | Requirement | How it's delivered |
|---|-------------|--------------------|
| 1 | Get source & target database | `--source-file`/`--source-url` + `--target-engine` (CLI) or `MigrationOptions` (API) |
| 2 | Analyze source, list objects in a table with target mapping, datatype & compatibility % | `analyzer.py` → tabular console output + Excel |
| 3 | Build target scripts as a folder | `generator.py` → `target_scripts/<engine>/…` |
| 3.1 | Subfolder per object type (table, procedure, function, view, …) | `tables/ views/ procedures/ functions/ triggers/ sequences/` |
| 3.2 | Excel file listing target object state | `target_object_state.xlsx` (Summary / Objects / Column Mapping / Effort) |
| 4 | Detailed source↔target status report + conversion effort | `reports/MIGRATION_STATUS_REPORT.md` + `reports/CONVERSION_EFFORT_REPORT.md` |
| 5 | README describing the plugin & how it works | this file |

---

## Quick start

```bash
# (optional) richer Excel formatting
pip install openpyxl

# Offline demo: Oracle sample DDL -> PostgreSQL (parses samples/oracle_sample_schema.sql)
python run_demo.py

# Live demo: builds a real SQLite DB and introspects it -> PostgreSQL
pip install SQLAlchemy
python run_live_demo.py
```

Or use the CLI directly:

```bash
# Offline: analyze a .sql / DDL dump
python -m dbmigrate \
    --source-file samples/oracle_sample_schema.sql \
    --source-engine oracle \
    --target-engine postgresql \
    --output-dir migration_output

# Live: introspect a running database (needs SQLAlchemy + a driver)
python -m dbmigrate \
    --source-url "postgresql+psycopg://user:pwd@host/dbname" \
    --target-engine mysql \
    --output-dir migration_output
```

---

## Two ways to read the source (both supported)

1. **Live DB connection** — `--source-url` uses SQLAlchemy's inspector to read
   tables, columns, keys, indexes and views from a running database.
   Requires `pip install SQLAlchemy` plus a driver
   (`oracledb`, `psycopg`, `pymysql`, `pyodbc`).
2. **DDL file (offline)** — `--source-file` parses a `.sql` dump with a
   dependency-free parser. Great for demos, air-gapped analysis, or when you
   only have a schema export.

If both are given, the live connection wins; the file acts as the fallback.

---

## Output layout

```
<output-dir>/
├── target_scripts/
│   └── <target-engine>/
│       ├── 00_run_all.sql        # master script (dependency-friendly order)
│       ├── tables/               # one converted CREATE TABLE per file
│       ├── views/
│       ├── procedures/
│       ├── functions/
│       ├── triggers/
│       └── sequences/
├── target_object_state.xlsx      # Summary | Objects | Column Mapping | Effort
└── reports/
    ├── MIGRATION_STATUS_REPORT.md    # object inventory + per-object status + datatype map
    └── CONVERSION_EFFORT_REPORT.md   # effort by type/risk + model + sequencing
```

- **Tables & sequences** are fully converted to target-dialect DDL.
- **Views** are copied with a review banner (vendor functions may need edits).
- **Procedures / functions / triggers**:
  - For **Oracle → PostgreSQL**, they are **auto-translated** PL/SQL → PL/pgSQL
    (parameters, `DECLARE` types, `NVL→COALESCE`, `SYSDATE→CURRENT_TIMESTAMP`,
    `seq.NEXTVAL→nextval('seq')`, `FROM DUAL` removal, `DBMS_OUTPUT→RAISE NOTICE`,
    and triggers split into a trigger-function + `CREATE TRIGGER`). Each file
    carries a **confidence score** and **translation notes**, and keeps the
    original source as a commented reference block.
  - For all other engine pairs, they are copied under a clearly-marked
    "MANUAL REVIEW REQUIRED" banner, because procedural code does not convert 1:1.

### Procedural translation confidence

The translator is deliberately conservative: risky constructs (cursors,
`%TYPE`/`%ROWTYPE`, `EXCEPTION` handlers, `ROWNUM`, `BULK COLLECT`/`FORALL`,
`CONNECT BY`, `DBMS_*` calls, `MERGE`) are left in place, flagged in the notes,
and lower the confidence score rather than being silently mis-translated.

---

## How compatibility & effort are calculated

**Datatype compatibility (per column, 0–100%)** comes from mapping tables in
`dbmigrate/mapping/datatypes.py`:

| Score | Meaning |
|------:|---------|
| 100 | Exact / lossless equivalent |
| 85  | Safe, minor syntax/behaviour difference |
| 60  | Converts but needs review (precision/semantics/sizing) |
| ≤30 | No native equivalent; emulated / manual |

A table's compatibility is the average of its columns. Procedural objects
(views, procedures, functions, triggers) use conservative per-engine baselines
in `mapping/registry.py`.

**Target state** is derived from compatibility:
`Automatic` (≥90%) · `Review` (60–89%) · `Manual` (<60%).

**Effort (hours)** per object:

```
hours = base_hours[type] × (1 + (100 − compatibility)/100 × 3) × constraint_factor
```

Base hours: table 1.0 · view 1.5 · procedure 4.0 · function 3.0 · trigger 2.5 ·
sequence 0.25. The `CONVERSION_EFFORT_REPORT.md` explains this and breaks effort
down by object type and risk band.

> These are static-analysis planning estimates. They do **not** include
> business-logic complexity, testing, or data migration/reconciliation — scope
> those separately.

---

## Supported engine pairs

Fully mapped datatype tables ship for:

- Oracle → PostgreSQL  *(also auto-translates PL/SQL routines & triggers)*
- SQL Server → PostgreSQL
- MySQL/MariaDB → PostgreSQL
- SQLite → PostgreSQL
- MySQL → Oracle
- Oracle → MySQL
- SQL Server → MySQL
- PostgreSQL → Oracle
- PostgreSQL → MySQL

Any other pair falls back to a **generic ANSI mapping** (lower compatibility,
flagged for review). Adding a new pair is one dictionary in `datatypes.py`;
adding a procedural translator is one entry in `translation/registry.py`.

---

## Architecture

```
dbmigrate/
├── model.py            # engine-neutral schema object model
├── connectors/         # source input
│   ├── ddl_file.py     #   offline DDL parser (zero deps)
│   └── live_db.py      #   SQLAlchemy introspection (optional dep)
├── mapping/            # extensible mapping registry
│   ├── datatypes.py    #   (source,target) -> datatype rules + compatibility
│   └── registry.py     #   public map API + object-level baselines
├── translation/        # best-effort procedural code translation
│   ├── plsql_pg.py     #   Oracle PL/SQL -> PostgreSQL PL/pgSQL
│   └── registry.py     #   translator lookup by engine pair
├── analyzer.py         # builds column maps, object analysis, effort, roll-ups
├── generator.py        # writes target-scripts folder tree + master script
├── reporting/          # console table, Excel workbook, Markdown reports
├── plugin.py           # orchestrator (MigrationPlugin / MigrationOptions)
└── cli.py              # argparse CLI (python -m dbmigrate)
```

Data flows one way and is decoupled at each stage:

```
source (file|db) → Schema model → analyze() → { scripts, Excel, reports }
```

Because every connector produces the same `Schema` model, and every mapping is
a data table, the plugin extends cleanly to new engines and new report formats.

---

## Programmatic use

```python
from dbmigrate import MigrationPlugin, MigrationOptions

outcome = MigrationPlugin(MigrationOptions(
    target_engine="postgresql",
    source_engine="oracle",
    source_file="samples/oracle_sample_schema.sql",
    output_dir="migration_output",
)).run()

print(outcome.analysis.total_effort(), "hours")
print(outcome.excel_path)
```

---

## Dependencies

- **Core: none** (Python 3.9+ standard library only; includes a native `.xlsx`
  writer fallback).
- **Optional:** `openpyxl` (formatted Excel), `SQLAlchemy` + a DB driver (live
  introspection). See `requirements.txt`.

---

## Limitations / notes

- The offline DDL parser is pragmatic, not a full SQL grammar; it targets common
  `CREATE` statement forms and Oracle `/` / T-SQL `GO` batch terminators.
- Procedural code is never blindly translated — it is preserved for guided
  manual rewrite.
- Data migration (rows), performance tuning and app-side changes are out of
  scope by design; this tool focuses on schema/object analysis and scaffolding.
```
