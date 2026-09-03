"""Public mapping API: datatype mapping + object-level compatibility scoring."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ..model import Column
from . import datatypes as dt

SUPPORTED_ENGINES = ["oracle", "sqlserver", "mysql", "postgresql", "mariadb", "sqlite", "db2"]

# Aliases so callers can be loose about engine naming.
_ENGINE_ALIASES = {
    "mssql": "sqlserver",
    "sql server": "sqlserver",
    "sqlserver": "sqlserver",
    "postgres": "postgresql",
    "pg": "postgresql",
    "postgresql": "postgresql",
    "mariadb": "mysql",
    "oracle": "oracle",
    "mysql": "mysql",
    "sqlite": "sqlite",
    "db2": "db2",
}


def normalize_engine(name: str) -> str:
    return _ENGINE_ALIASES.get(name.strip().lower(), name.strip().lower())


@dataclass
class TypeMapping:
    source_type: str
    target_type: str
    compatibility: int      # 0-100
    note: str
    used_generic: bool


def map_datatype(source_engine: str, target_engine: str, col: Column) -> TypeMapping:
    """Map a single column's datatype from source to target engine."""
    se, te = normalize_engine(source_engine), normalize_engine(target_engine)
    table = dt.get_map(se, te)
    rule = None
    used_generic = False

    if table is not None:
        rule = table.get(col.base_type.upper())

    if rule is None:
        rule = dt.generic_ansi_rule(col.base_type)
        used_generic = True

    target_type = dt.render(rule, col)
    return TypeMapping(
        source_type=col.raw_type,
        target_type=target_type,
        compatibility=rule.compatibility,
        note=rule.note,
        used_generic=used_generic,
    )


# --------------------------------------------------------------------------- #
# Object-level compatibility (procedures/functions/triggers/views/sequences).
#
# Procedural code (PL/SQL, T-SQL) rarely converts 1:1, so we give conservative
# baselines per (source, target) family and object type. These drive the
# effort estimate. Values are deliberately transparent & tunable.
# --------------------------------------------------------------------------- #
_PROCEDURAL_BASELINE = {
    # (source, target): {object_type: compatibility%}
    ("oracle", "postgresql"): {
        "view": 80, "procedure": 55, "function": 55, "trigger": 45, "sequence": 90,
    },
    ("sqlserver", "postgresql"): {
        "view": 80, "procedure": 50, "function": 50, "trigger": 45, "sequence": 85,
    },
    ("mysql", "postgresql"): {
        "view": 85, "procedure": 65, "function": 65, "trigger": 60, "sequence": 70,
    },
    ("sqlserver", "mysql"): {
        "view": 75, "procedure": 45, "function": 45, "trigger": 40, "sequence": 40,
    },
    ("oracle", "mysql"): {
        "view": 75, "procedure": 45, "function": 45, "trigger": 40, "sequence": 40,
    },
    ("postgresql", "oracle"): {
        "view": 80, "procedure": 55, "function": 55, "trigger": 45, "sequence": 85,
    },
    ("postgresql", "mysql"): {
        "view": 80, "procedure": 55, "function": 55, "trigger": 50, "sequence": 40,
    },
    ("sqlite", "postgresql"): {
        "view": 90, "procedure": 60, "function": 60, "trigger": 55, "sequence": 60,
    },
}
_DEFAULT_PROCEDURAL = {
    "view": 70, "procedure": 45, "function": 45, "trigger": 40, "sequence": 75,
}


def map_object_compatibility(source_engine: str, target_engine: str, object_type: str) -> int:
    se, te = normalize_engine(source_engine), normalize_engine(target_engine)
    baseline = _PROCEDURAL_BASELINE.get((se, te), _DEFAULT_PROCEDURAL)
    return baseline.get(object_type, 60)
