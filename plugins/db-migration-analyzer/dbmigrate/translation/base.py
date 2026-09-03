from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class TranslationResult:
    code: str                       # translated target-dialect code
    confidence: int                 # 0-100 (how safe the auto-translation is)
    translated: bool                # True if a translator ran, False if copied
    notes: List[str] = field(default_factory=list)
    original: str = ""              # source code, kept for reference
