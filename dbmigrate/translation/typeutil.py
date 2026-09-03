"""Map a bare SQL type *string* (as found in routine params/declarations) to a
target-engine type, reusing the DDL type parser and the datatype registry."""
from __future__ import annotations

from ..connectors.ddl_file import _parse_type
from ..mapping import map_datatype
from ..model import Column


def map_type_string(source_engine: str, target_engine: str, type_str: str) -> str:
    type_str = type_str.strip().rstrip(";,")
    if not type_str:
        return type_str
    base, length, precision, scale, _ = _parse_type(type_str)
    if not base:
        return type_str
    raw = base
    if precision is not None and scale is not None:
        raw = f"{base}({precision},{scale})"
    elif precision is not None:
        raw = f"{base}({precision})"
    elif length is not None:
        raw = f"{base}({length})"
    col = Column(name="_", raw_type=raw, base_type=base,
                 length=length, precision=precision, scale=scale)
    return map_datatype(source_engine, target_engine, col).target_type
