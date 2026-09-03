"""Command-line interface for the dbmigrate plugin.

Examples
--------
Offline DDL file:
    python -m dbmigrate --source-file samples/oracle_sample_schema.sql \
        --source-engine oracle --target-engine postgresql --output-dir out

Live database:
    python -m dbmigrate --source-url "postgresql+psycopg://u:p@host/db" \
        --target-engine mysql --output-dir out
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys

from .mapping import SUPPORTED_ENGINES
from .plugin import MigrationOptions, MigrationPlugin


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dbmigrate",
        description="Analyze a source database, map it to a target engine, "
                    "generate target scripts and migration/effort reports.")
    src = p.add_argument_group("source (choose one input)")
    src.add_argument("--source-file", help="Path to a .sql/DDL dump (offline path).")
    src.add_argument("--source-url", help="SQLAlchemy URL for live introspection.")
    src.add_argument("--source-engine",
                     help=f"Source engine (required with --source-file). "
                          f"One of: {', '.join(SUPPORTED_ENGINES)}")
    src.add_argument("--source-schema", help="Schema/owner to introspect (live only).")

    p.add_argument("--target-engine", required=True,
                   help=f"Target engine. One of: {', '.join(SUPPORTED_ENGINES)}")
    p.add_argument("--output-dir", default="migration_output",
                   help="Where to write scripts, Excel and reports.")
    p.add_argument("--quiet", action="store_true", help="Suppress the console table.")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.source_file and not args.source_url:
        print("error: provide --source-file or --source-url", file=sys.stderr)
        return 2

    options = MigrationOptions(
        target_engine=args.target_engine,
        source_engine=args.source_engine,
        source_file=args.source_file,
        source_url=args.source_url,
        source_schema=args.source_schema,
        output_dir=args.output_dir,
        generated_at=_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    try:
        outcome = MigrationPlugin(options).run()
    except Exception as exc:  # surface clean errors to the CLI user
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(outcome.console_text)

    print("\nArtifacts written:")
    print(f"  Target scripts : {outcome.scripts['root']}")
    print(f"  Master script  : {outcome.scripts['master']}")
    print(f"  Excel workbook : {outcome.excel_path}")
    print(f"  Status report  : {outcome.reports['status']}")
    print(f"  Effort report  : {outcome.reports['effort']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
