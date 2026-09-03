"""Source-schema connectors.

Two input paths (per user requirement: support both):
  * :class:`DDLFileConnector` - parse offline .sql / DDL dump files.
  * :class:`LiveDBConnector`  - introspect a running database via SQLAlchemy.

Both return an engine-neutral :class:`~dbmigrate.model.Schema`.
"""
from .base import SchemaConnector
from .ddl_file import DDLFileConnector
from .live_db import LiveDBConnector, build_connector

__all__ = [
    "SchemaConnector",
    "DDLFileConnector",
    "LiveDBConnector",
    "build_connector",
]
