"""Історія змін для Undo/Redo.

Зберігаються знімки шаблону (словники, як у JSON) до і після кожної дії.
Кілька послідовних змін одного поля (наприклад, набір тексту чи кроки
лічильника) зливаються в одну дію, якщо в них однаковий merge_key.
"""
from __future__ import annotations

from dataclasses import dataclass

LIMIT = 200


@dataclass
class Step:
    before: dict
    after: dict
    label: str
    merge_key: str | None


class History:
    def __init__(self, limit: int = LIMIT):
        self.limit = limit
        self._undo: list[Step] = []
        self._redo: list[Step] = []
        self._sealed = False  # наступна дія не зливається з попередньою

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def push(self, before: dict, after: dict, label: str, merge_key: str | None = None) -> None:
        if before == after:
            return
        self._redo.clear()
        last = self._undo[-1] if self._undo else None
        if (last is not None and merge_key is not None and not self._sealed
                and last.merge_key == merge_key and last.after == before):
            last.after = after
        else:
            self._undo.append(Step(before, after, label, merge_key))
            if len(self._undo) > self.limit:
                self._undo.pop(0)
        self._sealed = False

    def seal(self) -> None:
        """Завершити злиття: наступна зміна стане окремою дією."""
        self._sealed = True

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    def redo_label(self) -> str:
        return self._redo[-1].label if self._redo else ""

    def undo(self) -> dict | None:
        if not self._undo:
            return None
        step = self._undo.pop()
        self._redo.append(step)
        self._sealed = True
        return step.before

    def redo(self) -> dict | None:
        if not self._redo:
            return None
        step = self._redo.pop()
        self._undo.append(step)
        self._sealed = True
        return step.after
