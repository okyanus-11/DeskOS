"""Fuzzy matching used by the launcher and the command palette.

The scorer is a compact subsequence matcher with bonuses for word starts and
consecutive runs, which ranks "open terminal" above "open text editor" for the
query "term" while still matching loose abbreviations such as "st" -> "system
status".
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TypeVar

T = TypeVar("T")

_WORD_SEPARATORS = " \t-_/.:"
_BASE = 6
_CONSECUTIVE_BONUS = 8
_WORD_START_BONUS = 10
_CAMEL_BONUS = 6


def fuzzy_score(query: str, text: str) -> int | None:
    """Return a similarity score (higher is better) or ``None`` if unmatched."""
    if not query:
        return 0
    haystack = text.lower()
    needle = query.lower().strip()
    if not needle:
        return 0

    if needle in haystack:
        # Whole-word and prefix matches outrank scattered subsequences.
        if haystack.startswith(needle):
            return 1000 + (1000 - len(haystack))
        if f" {needle}" in haystack or f"-{needle}" in haystack:
            return 900 + (1000 - len(haystack))
        return 700 + (1000 - len(haystack))

    score = 0
    pos = 0
    previous_index = -2
    for char in needle:
        index = haystack.find(char, pos)
        if index == -1:
            return None
        score += _BASE
        if index == previous_index + 1:
            score += _CONSECUTIVE_BONUS
        if index == 0 or haystack[index - 1] in _WORD_SEPARATORS:
            score += _WORD_START_BONUS
        elif text[index].isupper() and text[index - 1].islower():
            score += _CAMEL_BONUS
        score -= min(index - pos, 4)
        previous_index = index
        pos = index + 1
    return score


def fuzzy_match(query: str, candidates: Sequence[tuple[T, str]]) -> list[tuple[T, int]]:
    """Rank ``(item, text)`` pairs by match quality, best first."""
    scored: list[tuple[T, int]] = []
    for item, text in candidates:
        value = fuzzy_score(query, text)
        if value is not None:
            scored.append((item, value))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def filter_items(query: str, items: Iterable[T], key=lambda item: str(item)) -> list[T]:
    """Convenience wrapper returning just the matching items, best match first."""
    return [item for item, _ in fuzzy_match(query, [(item, key(item)) for item in items])]
