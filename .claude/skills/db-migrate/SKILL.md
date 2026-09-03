---
name: db-migrate
description: >
  Analyze a source database and plan/scaffold a migration to a target engine.
  Use when the user wants to migrate a database, compare source vs target
  datatypes, estimate conversion effort, or generate target DDL/scripts.
  Supports Oracle, SQL Server, MySQL, PostgreSQL and SQLite via a live
  connection or an offline .sql/DDL file.
allowed-tools: Bash(python -m dbmigrate:*)
---

# Database Migration Analyzer

This skill runs the `dbmigrate` plugin, which:

1. Reads a **source** schema (live DB via SQLAlchemy URL, or an offline DDL file).
2. Analyzes every object and maps it to the **target** engine with a
   datatype-level **compatibility %**.
3. Generates a target-scripts folder tree (one subfolder per object type).
4. Writes an **Excel** workbook of target object state.
5. Writes detailed **status** and **conversion-effort** reports.

## How to run it

The Python package lives at the repo root (`C:\Dev\DBMigration`, which contains
the `dbmigrate/` package). Run the module from there:

```bash
# Offline DDL file
python -m dbmigrate \
  --source-file "<path/to/schema.sql>" \
  --source-engine <oracle|sqlserver|mysql|postgresql|sqlite> \
  --target-engine <oracle|sqlserver|mysql|postgresql> \
  --output-dir "<output-folder>"

# Live database (needs: pip install SQLAlchemy + a driver)
python -m dbmigrate \
  --source-url "postgresql+psycopg://user:pwd@host/db" \
  --target-engine mysql \
  --output-dir "<output-folder>"
```

If `python -m dbmigrate` is not found, run it from the repo root that contains
the `dbmigrate/` package, or set `PYTHONPATH` to that directory.

## What to ask the user first

- **Source**: a live connection URL, or a path to a `.sql`/DDL file (+ its engine)?
- **Target engine**?
- **Output directory**?

Then run the command, and summarize the console output plus the paths to the
generated scripts, Excel workbook, and reports. Full details: `README.md`.
