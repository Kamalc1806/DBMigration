"""Live-database connector using SQLAlchemy's cross-engine inspector.

SQLAlchemy is an *optional* dependency. If it (and the relevant DB driver) is
not installed, importing/using this connector raises a clear error telling the
user how to enable it, and the plugin can still run via the DDL-file path.

Supported URLs (examples):
    oracle+oracledb://user:pwd@host:1521/?service_name=ORCL
    mssql+pyodbc://user:pwd@dsn
    mysql+pymysql://user:pwd@host/dbname
    postgresql+psycopg://user:pwd@host/dbname
"""
from __future__ import annotations

from typing import Optional

from ..model import Column, Constraint, Index, Schema, Table, View
from .base import SchemaConnector


def _dialect_to_engine(dialect_name: str) -> str:
    d = dialect_name.lower()
    if d.startswith("oracle"):
        return "oracle"
    if d.startswith("mssql") or "sqlserver" in d:
        return "sqlserver"
    if d.startswith("mysql") or d.startswith("mariadb"):
        return "mysql"
    if d.startswith("postgres"):
        return "postgresql"
    return d


class LiveDBConnector(SchemaConnector):
    def __init__(self, url: str, schema: Optional[str] = None, engine: Optional[str] = None):
        self.url = url
        self.schema_name = schema
        self.engine_override = engine

    def extract(self) -> Schema:
        try:
            from sqlalchemy import create_engine, inspect
        except ImportError as exc:  # pragma: no cover - depends on env
            raise RuntimeError(
                "Live-DB introspection requires SQLAlchemy (and a DB driver).\n"
                "Install with:  pip install SQLAlchemy\n"
                "plus a driver, e.g.  pip install oracledb | pymysql | psycopg | pyodbc\n"
                "Alternatively use the DDL-file input path (--source-file)."
            ) from exc

        eng = create_engine(self.url)
        insp = inspect(eng)
        engine_name = self.engine_override or _dialect_to_engine(eng.dialect.name)
        schema = Schema(engine=engine_name, name=self.schema_name or eng.dialect.name)

        for tname in insp.get_table_names(schema=self.schema_name):
            table = Table(name=tname)
            for col in insp.get_columns(tname, schema=self.schema_name):
                raw_type = str(col["type"])
                base, length, precision, scale = _decompose_sa_type(col["type"], raw_type)
                table.columns.append(Column(
                    name=col["name"], raw_type=raw_type, base_type=base,
                    length=length, precision=precision, scale=scale,
                    nullable=col.get("nullable", True),
                    default=str(col.get("default")) if col.get("default") is not None else None,
                ))
            pk = insp.get_pk_constraint(tname, schema=self.schema_name)
            if pk and pk.get("constrained_columns"):
                table.constraints.append(Constraint(
                    pk.get("name") or f"pk_{tname}", "PRIMARY KEY",
                    list(pk["constrained_columns"])))
            for i, fk in enumerate(insp.get_foreign_keys(tname, schema=self.schema_name)):
                table.constraints.append(Constraint(
                    fk.get("name") or f"fk_{tname}_{i+1}", "FOREIGN KEY",
                    list(fk.get("constrained_columns", [])),
                    definition=f"REFERENCES {fk.get('referred_table')}"
                               f"({', '.join(fk.get('referred_columns', []))})"))
            for ix in insp.get_indexes(tname, schema=self.schema_name):
                table.indexes.append(Index(
                    ix.get("name") or f"ix_{tname}", list(ix.get("column_names", [])),
                    unique=ix.get("unique", False)))
            schema.tables.append(table)

        try:
            for vname in insp.get_view_names(schema=self.schema_name):
                definition = insp.get_view_definition(vname, schema=self.schema_name) or ""
                schema.views.append(View(name=vname, definition=definition))
        except NotImplementedError:  # pragma: no cover - dialect dependent
            pass

        return schema


def _decompose_sa_type(sa_type, raw_type: str):
    base = type(sa_type).__name__.upper()
    length = getattr(sa_type, "length", None)
    precision = getattr(sa_type, "precision", None)
    scale = getattr(sa_type, "scale", None)
    # Prefer the vendor spelling in the raw string where possible.
    import re
    m = re.match(r"([A-Za-z][A-Za-z0-9_ ]*?)\s*(\(|$)", raw_type)
    if m:
        base = m.group(1).strip().upper()
    return base, length, precision, scale


def build_connector(engine: Optional[str], source_file: Optional[str],
                    source_url: Optional[str], schema: Optional[str] = None) -> SchemaConnector:
    """Factory: choose DDL-file vs live-DB connector based on what's provided.

    Precedence: an explicit --source-url uses the live connector; otherwise a
    --source-file uses the DDL parser. This is the "connection + file fallback"
    behaviour requested.
    """
    from .ddl_file import DDLFileConnector
    if source_url:
        return LiveDBConnector(source_url, schema=schema, engine=engine)
    if source_file:
        if not engine:
            raise ValueError("--source-engine is required when using --source-file")
        return DDLFileConnector(source_file, engine=engine)
    raise ValueError("Provide either --source-url (live) or --source-file (DDL).")
