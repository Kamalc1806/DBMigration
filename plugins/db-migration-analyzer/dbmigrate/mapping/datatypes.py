"""Datatype mapping tables, keyed by (source_engine, target_engine).

Each entry maps a normalized *source base type* to a
:class:`TypeRule` describing the target type and how cleanly it converts.

`compatibility` is a 0-100 score for the datatype itself:
    100  = exact / lossless semantic equivalent
     85  = safe but with minor syntax/behaviour differences
     60  = converts but needs review (precision, semantics, sizing)
     30  = no native equivalent; emulated / manual work required

To add a new engine pair, just add a dict to ``DATATYPE_MAPS``. Anything not
found falls back to :func:`generic_ansi_rule`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..model import Column


@dataclass
class TypeRule:
    target_template: str        # may contain {length},{precision},{scale}
    compatibility: int
    note: str = ""


def render(rule: TypeRule, col: Column) -> str:
    """Fill a target template using the column's length/precision/scale.

    Missing precision/scale/length collapse cleanly so we never emit
    ``NUMERIC(,)`` or ``VARCHAR()``.
    """
    length = col.length if col.length is not None else ""
    precision = col.precision if col.precision is not None else ""
    scale = col.scale if col.scale is not None else ""
    try:
        text = rule.target_template.format(length=length, precision=precision, scale=scale)
    except (KeyError, IndexError):
        return rule.target_template
    # tidy up empty argument lists left by absent precision/scale/length
    text = re.sub(r"\(\s*,\s*\)", "", text)   # (,)  -> (removed)
    text = re.sub(r",\s*\)", ")", text)         # (6,) -> (6)
    text = re.sub(r"\(\s*,", "(", text)         # (,2) -> (2)
    text = text.replace("()", "")
    return text.strip()


# --------------------------------------------------------------------------- #
# ORACLE  ->  POSTGRESQL
# --------------------------------------------------------------------------- #
ORACLE_TO_PG: Dict[str, TypeRule] = {
    "VARCHAR2":  TypeRule("VARCHAR({length})", 100, "Direct equivalent."),
    "NVARCHAR2": TypeRule("VARCHAR({length})", 95, "PostgreSQL VARCHAR is Unicode by default."),
    "CHAR":      TypeRule("CHAR({length})", 100),
    "NCHAR":     TypeRule("CHAR({length})", 95, "Unicode by default in PG."),
    "CLOB":      TypeRule("TEXT", 95, "TEXT has no length limit."),
    "NCLOB":     TypeRule("TEXT", 95),
    "LONG":      TypeRule("TEXT", 80, "Deprecated Oracle type; map to TEXT."),
    "NUMBER":    TypeRule("NUMERIC({precision},{scale})", 90,
                          "NUMBER without precision -> NUMERIC (unbounded); consider INT/BIGINT for ids."),
    "FLOAT":     TypeRule("DOUBLE PRECISION", 85),
    "BINARY_FLOAT":  TypeRule("REAL", 85),
    "BINARY_DOUBLE": TypeRule("DOUBLE PRECISION", 85),
    "INTEGER":   TypeRule("INTEGER", 100),
    "INT":       TypeRule("INTEGER", 100),
    "SMALLINT":  TypeRule("SMALLINT", 100),
    "DATE":      TypeRule("TIMESTAMP(0)", 70,
                          "Oracle DATE holds a time component; PG DATE does not. Use TIMESTAMP to be safe."),
    "TIMESTAMP": TypeRule("TIMESTAMP", 95),
    "TIMESTAMP WITH TIME ZONE": TypeRule("TIMESTAMPTZ", 95),
    "TIMESTAMP WITH LOCAL TIME ZONE": TypeRule("TIMESTAMPTZ", 80, "Local-TZ semantics differ."),
    "RAW":       TypeRule("BYTEA", 85, "Length is ignored by BYTEA."),
    "LONG RAW":  TypeRule("BYTEA", 80),
    "BLOB":      TypeRule("BYTEA", 90),
    "BFILE":     TypeRule("TEXT", 30, "No PG equivalent; store path/reference and handle in app."),
    "ROWID":     TypeRule("TEXT", 30, "Oracle physical rowid has no PG equivalent."),
    "UROWID":    TypeRule("TEXT", 30),
    "XMLTYPE":   TypeRule("XML", 85),
    "INTERVAL YEAR TO MONTH": TypeRule("INTERVAL", 80),
    "INTERVAL DAY TO SECOND": TypeRule("INTERVAL", 80),
}

# --------------------------------------------------------------------------- #
# SQL SERVER  ->  POSTGRESQL
# --------------------------------------------------------------------------- #
SQLSERVER_TO_PG: Dict[str, TypeRule] = {
    "BIT":            TypeRule("BOOLEAN", 90, "0/1 -> false/true."),
    "TINYINT":        TypeRule("SMALLINT", 90, "SQL Server TINYINT is 0-255, unsigned."),
    "SMALLINT":       TypeRule("SMALLINT", 100),
    "INT":            TypeRule("INTEGER", 100),
    "BIGINT":         TypeRule("BIGINT", 100),
    "DECIMAL":        TypeRule("NUMERIC({precision},{scale})", 100),
    "NUMERIC":        TypeRule("NUMERIC({precision},{scale})", 100),
    "MONEY":          TypeRule("NUMERIC(19,4)", 85, "Map MONEY to fixed NUMERIC."),
    "SMALLMONEY":     TypeRule("NUMERIC(10,4)", 85),
    "FLOAT":          TypeRule("DOUBLE PRECISION", 90),
    "REAL":           TypeRule("REAL", 100),
    "CHAR":           TypeRule("CHAR({length})", 100),
    "NCHAR":          TypeRule("CHAR({length})", 95),
    "VARCHAR":        TypeRule("VARCHAR({length})", 100),
    "NVARCHAR":       TypeRule("VARCHAR({length})", 95, "PG VARCHAR is Unicode."),
    "TEXT":           TypeRule("TEXT", 95),
    "NTEXT":          TypeRule("TEXT", 95),
    "DATE":           TypeRule("DATE", 100),
    "DATETIME":       TypeRule("TIMESTAMP", 90, "Lower fractional-second precision in old DATETIME."),
    "DATETIME2":      TypeRule("TIMESTAMP", 95),
    "SMALLDATETIME":  TypeRule("TIMESTAMP(0)", 90),
    "DATETIMEOFFSET": TypeRule("TIMESTAMPTZ", 90),
    "TIME":           TypeRule("TIME", 95),
    "UNIQUEIDENTIFIER": TypeRule("UUID", 95),
    "BINARY":         TypeRule("BYTEA", 85),
    "VARBINARY":      TypeRule("BYTEA", 85),
    "IMAGE":          TypeRule("BYTEA", 80, "Deprecated type."),
    "XML":            TypeRule("XML", 90),
    "SQL_VARIANT":    TypeRule("TEXT", 30, "No equivalent; requires app-level handling."),
    "HIERARCHYID":    TypeRule("TEXT", 30, "No native equivalent; consider ltree extension."),
    "GEOGRAPHY":      TypeRule("GEOGRAPHY", 40, "Requires PostGIS extension."),
    "GEOMETRY":       TypeRule("GEOMETRY", 40, "Requires PostGIS extension."),
}

# --------------------------------------------------------------------------- #
# MYSQL  ->  POSTGRESQL
# --------------------------------------------------------------------------- #
MYSQL_TO_PG: Dict[str, TypeRule] = {
    "TINYINT":    TypeRule("SMALLINT", 90, "TINYINT(1) is often boolean in MySQL."),
    "SMALLINT":   TypeRule("SMALLINT", 100),
    "MEDIUMINT":  TypeRule("INTEGER", 95),
    "INT":        TypeRule("INTEGER", 100),
    "INTEGER":    TypeRule("INTEGER", 100),
    "BIGINT":     TypeRule("BIGINT", 100),
    "DECIMAL":    TypeRule("NUMERIC({precision},{scale})", 100),
    "NUMERIC":    TypeRule("NUMERIC({precision},{scale})", 100),
    "FLOAT":      TypeRule("REAL", 95),
    "DOUBLE":     TypeRule("DOUBLE PRECISION", 100),
    "BIT":        TypeRule("BIT({length})", 85),
    "CHAR":       TypeRule("CHAR({length})", 100),
    "VARCHAR":    TypeRule("VARCHAR({length})", 100),
    "TINYTEXT":   TypeRule("TEXT", 95),
    "TEXT":       TypeRule("TEXT", 100),
    "MEDIUMTEXT": TypeRule("TEXT", 100),
    "LONGTEXT":   TypeRule("TEXT", 100),
    "ENUM":       TypeRule("VARCHAR(255)", 60, "Convert to VARCHAR + CHECK, or a PG ENUM type."),
    "SET":        TypeRule("TEXT", 40, "No native equivalent; emulate with array/check."),
    "DATE":       TypeRule("DATE", 100),
    "DATETIME":   TypeRule("TIMESTAMP", 95),
    "TIMESTAMP":  TypeRule("TIMESTAMPTZ", 85, "MySQL TIMESTAMP auto-updates; behaviour differs."),
    "TIME":       TypeRule("TIME", 100),
    "YEAR":       TypeRule("SMALLINT", 70, "No YEAR type in PG."),
    "TINYBLOB":   TypeRule("BYTEA", 95),
    "BLOB":       TypeRule("BYTEA", 100),
    "MEDIUMBLOB": TypeRule("BYTEA", 100),
    "LONGBLOB":   TypeRule("BYTEA", 100),
    "BINARY":     TypeRule("BYTEA", 90),
    "VARBINARY":  TypeRule("BYTEA", 90),
    "JSON":       TypeRule("JSONB", 90, "JSONB recommended over JSON in PG."),
    "GEOMETRY":   TypeRule("GEOMETRY", 40, "Requires PostGIS."),
}

# --------------------------------------------------------------------------- #
# MYSQL  ->  ORACLE  (illustrates a non-PG target)
# --------------------------------------------------------------------------- #
MYSQL_TO_ORACLE: Dict[str, TypeRule] = {
    "TINYINT":   TypeRule("NUMBER(3)", 85),
    "SMALLINT":  TypeRule("NUMBER(5)", 90),
    "INT":       TypeRule("NUMBER(10)", 90),
    "INTEGER":   TypeRule("NUMBER(10)", 90),
    "BIGINT":    TypeRule("NUMBER(19)", 90),
    "DECIMAL":   TypeRule("NUMBER({precision},{scale})", 100),
    "FLOAT":     TypeRule("BINARY_FLOAT", 90),
    "DOUBLE":    TypeRule("BINARY_DOUBLE", 90),
    "CHAR":      TypeRule("CHAR({length})", 100),
    "VARCHAR":   TypeRule("VARCHAR2({length})", 95),
    "TEXT":      TypeRule("CLOB", 90),
    "LONGTEXT":  TypeRule("CLOB", 90),
    "DATETIME":  TypeRule("TIMESTAMP", 90),
    "DATE":      TypeRule("DATE", 95),
    "TIMESTAMP": TypeRule("TIMESTAMP", 85),
    "BLOB":      TypeRule("BLOB", 100),
    "JSON":      TypeRule("CLOB", 60, "Oracle 21c has JSON type; older versions use CLOB + IS JSON."),
}


# --------------------------------------------------------------------------- #
# SQL SERVER  ->  MYSQL
# --------------------------------------------------------------------------- #
SQLSERVER_TO_MYSQL: Dict[str, TypeRule] = {
    "BIT":            TypeRule("TINYINT(1)", 90, "0/1 boolean convention."),
    "TINYINT":        TypeRule("TINYINT UNSIGNED", 90, "SQL Server TINYINT is unsigned 0-255."),
    "SMALLINT":       TypeRule("SMALLINT", 100),
    "INT":            TypeRule("INT", 100),
    "BIGINT":         TypeRule("BIGINT", 100),
    "DECIMAL":        TypeRule("DECIMAL({precision},{scale})", 100),
    "NUMERIC":        TypeRule("DECIMAL({precision},{scale})", 100),
    "MONEY":          TypeRule("DECIMAL(19,4)", 85),
    "SMALLMONEY":     TypeRule("DECIMAL(10,4)", 85),
    "FLOAT":          TypeRule("DOUBLE", 90),
    "REAL":           TypeRule("FLOAT", 90),
    "CHAR":           TypeRule("CHAR({length})", 100),
    "NCHAR":          TypeRule("CHAR({length})", 95),
    "VARCHAR":        TypeRule("VARCHAR({length})", 100),
    "NVARCHAR":       TypeRule("VARCHAR({length})", 95, "Use utf8mb4 charset for Unicode."),
    "TEXT":           TypeRule("LONGTEXT", 90),
    "NTEXT":          TypeRule("LONGTEXT", 90),
    "DATE":           TypeRule("DATE", 100),
    "DATETIME":       TypeRule("DATETIME", 95),
    "DATETIME2":      TypeRule("DATETIME(6)", 90),
    "SMALLDATETIME":  TypeRule("DATETIME", 90),
    "DATETIMEOFFSET": TypeRule("DATETIME(6)", 70, "MySQL has no TZ-aware type; store UTC."),
    "TIME":           TypeRule("TIME", 95),
    "UNIQUEIDENTIFIER": TypeRule("CHAR(36)", 80, "Store GUID as CHAR(36)."),
    "BINARY":         TypeRule("BINARY({length})", 90),
    "VARBINARY":      TypeRule("VARBINARY({length})", 90),
    "IMAGE":          TypeRule("LONGBLOB", 80),
    "XML":            TypeRule("LONGTEXT", 60, "MySQL has no native XML type."),
    "SQL_VARIANT":    TypeRule("LONGTEXT", 30, "No equivalent; app-level handling."),
    "GEOGRAPHY":      TypeRule("GEOMETRY", 50, "MySQL spatial types differ from SQL Server."),
    "GEOMETRY":       TypeRule("GEOMETRY", 60),
}

# --------------------------------------------------------------------------- #
# ORACLE  ->  MYSQL
# --------------------------------------------------------------------------- #
ORACLE_TO_MYSQL: Dict[str, TypeRule] = {
    "VARCHAR2":  TypeRule("VARCHAR({length})", 95, "VARCHAR max 65535 bytes in MySQL."),
    "NVARCHAR2": TypeRule("VARCHAR({length})", 90, "Use utf8mb4."),
    "CHAR":      TypeRule("CHAR({length})", 100),
    "NCHAR":     TypeRule("CHAR({length})", 95),
    "CLOB":      TypeRule("LONGTEXT", 90),
    "NCLOB":     TypeRule("LONGTEXT", 90),
    "LONG":      TypeRule("LONGTEXT", 80),
    "NUMBER":    TypeRule("DECIMAL({precision},{scale})", 85,
                          "NUMBER w/o precision -> DECIMAL; consider INT/BIGINT for ids."),
    "FLOAT":     TypeRule("DOUBLE", 85),
    "BINARY_FLOAT":  TypeRule("FLOAT", 85),
    "BINARY_DOUBLE": TypeRule("DOUBLE", 85),
    "INTEGER":   TypeRule("INT", 100),
    "INT":       TypeRule("INT", 100),
    "SMALLINT":  TypeRule("SMALLINT", 100),
    "DATE":      TypeRule("DATETIME", 80, "Oracle DATE has a time component -> DATETIME."),
    "TIMESTAMP": TypeRule("DATETIME(6)", 90),
    "TIMESTAMP WITH TIME ZONE": TypeRule("DATETIME(6)", 65, "No TZ-aware type; store UTC."),
    "RAW":       TypeRule("VARBINARY({length})", 85),
    "LONG RAW":  TypeRule("LONGBLOB", 80),
    "BLOB":      TypeRule("LONGBLOB", 90),
    "BFILE":     TypeRule("VARCHAR(1024)", 30, "No equivalent; store path/reference."),
    "ROWID":     TypeRule("VARCHAR(64)", 30),
    "XMLTYPE":   TypeRule("LONGTEXT", 60),
}

# --------------------------------------------------------------------------- #
# POSTGRESQL  ->  ORACLE
# --------------------------------------------------------------------------- #
POSTGRESQL_TO_ORACLE: Dict[str, TypeRule] = {
    "SMALLINT":         TypeRule("NUMBER(5)", 90),
    "INTEGER":          TypeRule("NUMBER(10)", 90),
    "INT":              TypeRule("NUMBER(10)", 90),
    "BIGINT":           TypeRule("NUMBER(19)", 90),
    "SERIAL":           TypeRule("NUMBER(10)", 70, "Use a SEQUENCE + trigger/IDENTITY."),
    "BIGSERIAL":        TypeRule("NUMBER(19)", 70, "Use a SEQUENCE + trigger/IDENTITY."),
    "NUMERIC":          TypeRule("NUMBER({precision},{scale})", 100),
    "DECIMAL":          TypeRule("NUMBER({precision},{scale})", 100),
    "REAL":             TypeRule("BINARY_FLOAT", 90),
    "DOUBLE PRECISION": TypeRule("BINARY_DOUBLE", 90),
    "MONEY":            TypeRule("NUMBER(19,4)", 80),
    "CHAR":             TypeRule("CHAR({length})", 100),
    "VARCHAR":          TypeRule("VARCHAR2({length})", 95),
    "TEXT":             TypeRule("CLOB", 85),
    "BOOLEAN":          TypeRule("NUMBER(1)", 75, "Oracle has no BOOLEAN in SQL; use NUMBER(1) 0/1."),
    "DATE":             TypeRule("DATE", 90),
    "TIMESTAMP":        TypeRule("TIMESTAMP", 95),
    "TIMESTAMPTZ":      TypeRule("TIMESTAMP WITH TIME ZONE", 95),
    "TIME":             TypeRule("DATE", 60, "Oracle has no pure TIME type."),
    "BYTEA":            TypeRule("BLOB", 90),
    "UUID":             TypeRule("RAW(16)", 80, "Or VARCHAR2(36) for text form."),
    "JSON":             TypeRule("CLOB", 70, "Oracle 21c has JSON; older use CLOB + IS JSON."),
    "JSONB":            TypeRule("CLOB", 70),
    "XML":              TypeRule("XMLTYPE", 85),
    "INET":             TypeRule("VARCHAR2(45)", 50, "No native network type."),
    "ARRAY":            TypeRule("CLOB", 30, "No native array; use nested table/JSON."),
}

# --------------------------------------------------------------------------- #
# POSTGRESQL  ->  MYSQL
# --------------------------------------------------------------------------- #
POSTGRESQL_TO_MYSQL: Dict[str, TypeRule] = {
    "SMALLINT":         TypeRule("SMALLINT", 100),
    "INTEGER":          TypeRule("INT", 100),
    "INT":              TypeRule("INT", 100),
    "BIGINT":           TypeRule("BIGINT", 100),
    "SERIAL":           TypeRule("INT AUTO_INCREMENT", 80),
    "BIGSERIAL":        TypeRule("BIGINT AUTO_INCREMENT", 80),
    "NUMERIC":          TypeRule("DECIMAL({precision},{scale})", 100),
    "DECIMAL":          TypeRule("DECIMAL({precision},{scale})", 100),
    "REAL":             TypeRule("FLOAT", 95),
    "DOUBLE PRECISION": TypeRule("DOUBLE", 95),
    "CHAR":             TypeRule("CHAR({length})", 100),
    "VARCHAR":          TypeRule("VARCHAR({length})", 100),
    "TEXT":             TypeRule("LONGTEXT", 95),
    "BOOLEAN":          TypeRule("TINYINT(1)", 90),
    "DATE":             TypeRule("DATE", 100),
    "TIMESTAMP":        TypeRule("DATETIME(6)", 90),
    "TIMESTAMPTZ":      TypeRule("DATETIME(6)", 70, "No TZ-aware type; store UTC."),
    "TIME":             TypeRule("TIME", 95),
    "BYTEA":            TypeRule("LONGBLOB", 90),
    "UUID":             TypeRule("CHAR(36)", 80),
    "JSON":             TypeRule("JSON", 95),
    "JSONB":            TypeRule("JSON", 90),
    "XML":              TypeRule("LONGTEXT", 60),
    "INET":             TypeRule("VARCHAR(45)", 50),
    "ARRAY":            TypeRule("JSON", 40, "No native array; emulate with JSON."),
}


# --------------------------------------------------------------------------- #
# SQLITE  ->  POSTGRESQL   (SQLite is dynamically typed; map declared types)
# --------------------------------------------------------------------------- #
SQLITE_TO_PG: Dict[str, TypeRule] = {
    "INTEGER":  TypeRule("INTEGER", 95, "SQLite INTEGER is 64-bit; use BIGINT if large."),
    "INT":      TypeRule("INTEGER", 95),
    "BIGINT":   TypeRule("BIGINT", 100),
    "TINYINT":  TypeRule("SMALLINT", 90),
    "SMALLINT": TypeRule("SMALLINT", 100),
    "REAL":     TypeRule("DOUBLE PRECISION", 90),
    "FLOAT":    TypeRule("DOUBLE PRECISION", 90),
    "DOUBLE":   TypeRule("DOUBLE PRECISION", 100),
    "NUMERIC":  TypeRule("NUMERIC({precision},{scale})", 95),
    "DECIMAL":  TypeRule("NUMERIC({precision},{scale})", 95),
    "BOOLEAN":  TypeRule("BOOLEAN", 90, "SQLite stores booleans as 0/1 integers."),
    "TEXT":     TypeRule("TEXT", 100),
    "CLOB":     TypeRule("TEXT", 95),
    "CHAR":     TypeRule("CHAR({length})", 100),
    "VARCHAR":  TypeRule("VARCHAR({length})", 100),
    "NVARCHAR": TypeRule("VARCHAR({length})", 95),
    "BLOB":     TypeRule("BYTEA", 90),
    "DATE":     TypeRule("DATE", 85, "SQLite has no real DATE type; stored as TEXT/NUM."),
    "DATETIME": TypeRule("TIMESTAMP", 85, "Stored as TEXT/NUM in SQLite; verify format."),
    "TIMESTAMP": TypeRule("TIMESTAMP", 85),
    "TIME":     TypeRule("TIME", 85),
}


DATATYPE_MAPS: Dict[Tuple[str, str], Dict[str, TypeRule]] = {
    ("oracle", "postgresql"): ORACLE_TO_PG,
    ("sqlite", "postgresql"): SQLITE_TO_PG,
    ("sqlserver", "postgresql"): SQLSERVER_TO_PG,
    ("mysql", "postgresql"): MYSQL_TO_PG,
    ("mysql", "oracle"): MYSQL_TO_ORACLE,
    ("sqlserver", "mysql"): SQLSERVER_TO_MYSQL,
    ("oracle", "mysql"): ORACLE_TO_MYSQL,
    ("postgresql", "oracle"): POSTGRESQL_TO_ORACLE,
    ("postgresql", "mysql"): POSTGRESQL_TO_MYSQL,
}


# --------------------------------------------------------------------------- #
# Generic ANSI fallback for engine pairs / types with no explicit rule.
# --------------------------------------------------------------------------- #
_GENERIC_ANSI = {
    "INT": TypeRule("INTEGER", 80),
    "INTEGER": TypeRule("INTEGER", 80),
    "SMALLINT": TypeRule("SMALLINT", 80),
    "BIGINT": TypeRule("BIGINT", 80),
    "DECIMAL": TypeRule("DECIMAL({precision},{scale})", 75),
    "NUMERIC": TypeRule("NUMERIC({precision},{scale})", 75),
    "NUMBER": TypeRule("NUMERIC({precision},{scale})", 70),
    "FLOAT": TypeRule("FLOAT", 70),
    "REAL": TypeRule("REAL", 75),
    "DOUBLE": TypeRule("DOUBLE PRECISION", 70),
    "CHAR": TypeRule("CHAR({length})", 80),
    "VARCHAR": TypeRule("VARCHAR({length})", 80),
    "VARCHAR2": TypeRule("VARCHAR({length})", 70),
    "TEXT": TypeRule("VARCHAR(4000)", 60),
    "CLOB": TypeRule("TEXT", 60),
    "BLOB": TypeRule("BINARY LARGE OBJECT", 55),
    "DATE": TypeRule("DATE", 75),
    "DATETIME": TypeRule("TIMESTAMP", 70),
    "TIMESTAMP": TypeRule("TIMESTAMP", 75),
    "TIME": TypeRule("TIME", 75),
    "BOOLEAN": TypeRule("BOOLEAN", 80),
}


def generic_ansi_rule(base_type: str) -> TypeRule:
    rule = _GENERIC_ANSI.get(base_type.upper())
    if rule:
        # generic route always caps compatibility a bit lower + flags review
        return TypeRule(rule.target_template, min(rule.compatibility, 70),
                        "Generic ANSI mapping (no engine-specific rule); review recommended.")
    return TypeRule("VARCHAR(4000)", 25,
                    f"Unknown type '{base_type}': no mapping found. Manual conversion required.")


def get_map(source_engine: str, target_engine: str) -> Optional[Dict[str, TypeRule]]:
    return DATATYPE_MAPS.get((source_engine.lower(), target_engine.lower()))
