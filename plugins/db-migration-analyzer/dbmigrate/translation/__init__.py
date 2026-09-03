"""Best-effort procedural code translation.

Cross-dialect procedural translation can never be fully automatic, so each
translator returns a :class:`TranslationResult` carrying the converted code, a
**confidence** score, and human-readable **notes** about constructs that need
manual verification. The generator uses this to emit translated code *and* keep
the original for reference.

Currently implemented:
    * Oracle PL/SQL  ->  PostgreSQL PL/pgSQL  (routines + triggers)

Other engine pairs return ``None`` from :func:`get_translator`, so the
generator falls back to copy-with-review-banner behaviour.
"""
from .base import TranslationResult
from .registry import get_translator

__all__ = ["TranslationResult", "get_translator"]
