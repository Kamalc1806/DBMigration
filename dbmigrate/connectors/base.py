from __future__ import annotations

from abc import ABC, abstractmethod

from ..model import Schema


class SchemaConnector(ABC):
    """Produces an engine-neutral :class:`Schema` from some source."""

    @abstractmethod
    def extract(self) -> Schema:
        ...
