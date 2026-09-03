"""End-to-end LIVE demo: introspect a real SQLite database -> PostgreSQL.

Builds a small SQLite database, then runs the plugin against it through the
SQLAlchemy live-introspection path (no external DB server or driver needed).

Run:
    python run_live_demo.py
Produces everything under ./live_demo_output/.
"""
import datetime as dt
import os
import sqlite3

from dbmigrate import MigrationOptions, MigrationPlugin

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "samples", "live_sample.db")

_DDL = """
CREATE TABLE departments (
  dept_id   INTEGER PRIMARY KEY,
  dept_name VARCHAR(60) NOT NULL,
  budget    NUMERIC(14,2) DEFAULT 0
);
CREATE TABLE employees (
  emp_id     INTEGER PRIMARY KEY,
  first_name VARCHAR(50) NOT NULL,
  last_name  VARCHAR(50) NOT NULL,
  email      TEXT,
  hire_date  TEXT,
  salary     REAL,
  is_active  INTEGER DEFAULT 1,
  dept_id    INTEGER REFERENCES departments(dept_id)
);
CREATE UNIQUE INDEX ix_emp_email ON employees(email);
CREATE VIEW v_active AS
  SELECT emp_id, first_name, last_name FROM employees WHERE is_active = 1;
"""


def build_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_DDL)
    conn.commit()
    conn.close()


def main():
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        raise SystemExit("This demo needs SQLAlchemy:  pip install SQLAlchemy")

    build_db()
    options = MigrationOptions(
        target_engine="postgresql",
        source_url=f"sqlite:///{DB_PATH}",
        output_dir=os.path.join(HERE, "live_demo_output"),
        generated_at=dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    outcome = MigrationPlugin(options).run()
    print(outcome.console_text)
    print("\nArtifacts written under:", options.output_dir)


if __name__ == "__main__":
    main()
