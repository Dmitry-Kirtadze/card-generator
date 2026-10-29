"""Розрахунок прилипання: до країв і центру полотна, інших блоків і сітки.

Усе в координатах полотна. Чисті функції — легко тестувати.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Snap:
    delta: float = 0.0
    guide: float | None = None  # координата лінії-підказки


def snap_axis(edges: list[float], targets: list[float], threshold: float) -> Snap:
    """Найменший зсув, що суміщає будь-який край з будь-якою ціллю в межах порогу."""
    best: Snap | None = None
    for edge in edges:
        for target in targets:
            d = target - edge
            if abs(d) <= threshold and (best is None or abs(d) < abs(best.delta)):
                best = Snap(d, target)
    return best or Snap()


def grid_targets(edges: list[float], grid: float) -> list[float]:
    if grid <= 0:
        return []
    return [round(e / grid) * grid for e in edges]


def snap_rect(left: float, top: float, width: float, height: float, xs: list[float],
              ys: list[float], threshold: float, grid: float = 0) -> tuple[Snap, Snap]:
    """Прилипання прямокутника (краї й центр) по обох осях."""
    edges_x = [left, left + width / 2, left + width]
    edges_y = [top, top + height / 2, top + height]
    sx = snap_axis(edges_x, xs + grid_targets(edges_x, grid), threshold)
    sy = snap_axis(edges_y, ys + grid_targets(edges_y, grid), threshold)
    return sx, sy


def snap_value(value: float, targets: list[float], threshold: float, grid: float = 0) -> Snap:
    return snap_axis([value], targets + grid_targets([value], grid), threshold)


def snap_angle(angle: float, free_step: float | None = None, threshold: float = 3.0) -> float:
    """Кут у межах (-180, 180]. free_step — жорсткий крок (Shift), інакше прилипання до 45°."""
    if free_step:
        angle = round(angle / free_step) * free_step
    else:
        nearest = round(angle / 45) * 45
        if abs(angle - nearest) <= threshold:
            angle = nearest
    angle = math.fmod(angle, 360)
    if angle > 180:
        angle -= 360
    elif angle <= -180:
        angle += 360
    return round(angle, 2)
