"""Translator lookup by (source_engine, target_engine)."""
from __future__ import annotations

from typing import Callable, Optional

from ..mapping.registry import normalize_engine
from ..model import Routine, Trigger
from .base import TranslationResult
from . import plsql_pg


class Translator:
    """Bundle of per-object-kind translation functions for one engine pair."""

    def __init__(self, routine_fn: Callable[[Routine], TranslationResult],
                 trigger_fn: Callable[[Trigger], TranslationResult]):
        self._routine_fn = routine_fn
        self._trigger_fn = trigger_fn

    def routine(self, routine: Routine) -> TranslationResult:
        return self._routine_fn(routine)

    def trigger(self, trigger: Trigger) -> TranslationResult:
        return self._trigger_fn(trigger)


_TRANSLATORS = {
    ("oracle", "postgresql"): Translator(plsql_pg.translate_routine,
                                         plsql_pg.translate_trigger),
}


def get_translator(source_engine: str, target_engine: str) -> Optional[Translator]:
    return _TRANSLATORS.get((normalize_engine(source_engine),
                             normalize_engine(target_engine)))
