"""dbmigrate - a generic, extensible database migration analysis & scripting plugin.

Given a *source* database (via live connection or DDL files) and a *target*
engine, it:
  1. Extracts the source schema object model.
  2. Analyzes every object and maps it to the target engine, with a
     datatype-level compatibility percentage.
  3. Generates a target-scripts folder tree (one subfolder per object type).
  4. Produces an Excel workbook of target object state.
  5. Produces a detailed source/target status + conversion-effort report.
"""

from .plugin import MigrationPlugin, MigrationOptions

__all__ = ["MigrationPlugin", "MigrationOptions"]
__version__ = "1.0.0"
