"""Engine-neutral schema object model.

Every connector (live DB or DDL file) produces a :class:`Schema` made of these
dataclasses. Everything downstream (analysis, generation, reporting) consumes
this model, so the rest of the plugin never needs to know *how* the source was
read.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Column:
    name: str
    raw_type: str                       # e.g. "VARCHAR2(100)", "NUMBER(10,2)"
    base_type: str                      # normalized base, e.g. "VARCHAR2", "NUMBER"
    length: Optional[int] = None
    precision: Optional[int] = None
    scale: Optional[int] = None
    nullable: bool = True
    default: Optional[str] = None
    comment: Optional[str] = None


@dataclass
class Constraint:
    name: str
    kind: str                           # PRIMARY KEY | FOREIGN KEY | UNIQUE | CHECK
    columns: List[str] = field(default_factory=list)
    definition: Optional[str] = None    # raw text for CHECK / FK references


@dataclass
class Index:
    name: str
    columns: List[str] = field(default_factory=list)
    unique: bool = False


@dataclass
class Table:
    name: str
    columns: List[Column] = field(default_factory=list)
    constraints: List[Constraint] = field(default_factory=list)
    indexes: List[Index] = field(default_factory=list)
    comment: Optional[str] = None
    row_estimate: Optional[int] = None


@dataclass
class View:
    name: str
    definition: str                     # the SELECT body / full DDL


@dataclass
class Routine:
    """Procedure or function (kind distinguishes them)."""
    name: str
    kind: str                           # PROCEDURE | FUNCTION
    definition: str
    language: Optional[str] = None      # e.g. PL/SQL, T-SQL


@dataclass
class Trigger:
    name: str
    table: Optional[str]
    definition: str


@dataclass
class Sequence:
    name: str
    start: Optional[int] = None
    increment: Optional[int] = None


@dataclass
class Schema:
    """Full source schema, engine-tagged."""
    engine: str                         # oracle | sqlserver | mysql | postgresql | ...
    name: str = "source"
    tables: List[Table] = field(default_factory=list)
    views: List[View] = field(default_factory=list)
    routines: List[Routine] = field(default_factory=list)
    triggers: List[Trigger] = field(default_factory=list)
    sequences: List[Sequence] = field(default_factory=list)

    def object_counts(self) -> dict:
        procs = sum(1 for r in self.routines if r.kind == "PROCEDURE")
        funcs = sum(1 for r in self.routines if r.kind == "FUNCTION")
        return {
            "tables": len(self.tables),
            "views": len(self.views),
            "procedures": procs,
            "functions": funcs,
            "triggers": len(self.triggers),
            "sequences": len(self.sequences),
        }

    def all_objects(self):
        """Yield (object_type, name, obj) for every object in the schema."""
        for t in self.tables:
            yield ("table", t.name, t)
        for v in self.views:
            yield ("view", v.name, v)
        for r in self.routines:
            yield (r.kind.lower(), r.name, r)
        for tr in self.triggers:
            yield ("trigger", tr.name, tr)
        for s in self.sequences:
            yield ("sequence", s.name, s)
