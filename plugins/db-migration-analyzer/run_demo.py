"""End-to-end demo: Oracle sample schema -> PostgreSQL.

Run:
    python run_demo.py
Produces everything under ./demo_output/.
"""
import datetime as dt
import os

from dbmigrate import MigrationOptions, MigrationPlugin

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    options = MigrationOptions(
        target_engine="postgresql",
        source_engine="oracle",
        source_file=os.path.join(HERE, "samples", "oracle_sample_schema.sql"),
        output_dir=os.path.join(HERE, "demo_output"),
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    outcome = MigrationPlugin(options).run()
    print(outcome.console_text)
    print("\nArtifacts written:")
    print(f"  Target scripts : {outcome.scripts['root']}")
    print(f"  Master script  : {outcome.scripts['master']}")
    print(f"  Excel workbook : {outcome.excel_path}")
    print(f"  Status report  : {outcome.reports['status']}")
    print(f"  Effort report  : {outcome.reports['effort']}")


if __name__ == "__main__":
    main()
