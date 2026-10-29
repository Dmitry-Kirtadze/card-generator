"""Порівняння зображень для тестів відмальовування."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat
from PySide6.QtGui import QImage

GOLDEN_DIR = Path(__file__).parent / "golden"


def to_pil(image: QImage) -> Image.Image:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = image.width(), image.height()
    return Image.frombuffer("RGBA", (w, h), bytes(image.constBits()), "raw", "RGBA",
                            image.bytesPerLine(), 1).convert("RGB")


def difference(a: QImage, b: QImage) -> tuple[float, float]:
    """(середня різниця 0..255, частка пікселів, що відрізняються більш ніж на 40)."""
    pa, pb = to_pil(a), to_pil(b)
    assert pa.size == pb.size, f"розміри {pa.size} != {pb.size}"
    diff = ImageChops.difference(pa, pb).convert("L")
    mean = ImageStat.Stat(diff).mean[0]
    strong = sum(diff.point(lambda v: 255 if v > 40 else 0).histogram()[255:]) / (pa.width * pa.height)
    return mean, strong


def assert_matches_golden(image: QImage, name: str, *, mean_tol: float = 1.0,
                          strong_tol: float = 0.003) -> None:
    """Порівнює з еталоном tests/golden/<name>.png.

    Створити або оновити еталон: UPDATE_GOLDEN=1 pytest …
    Після оновлення еталон варто переглянути очима.
    """
    path = GOLDEN_DIR / f"{name}.png"
    if os.environ.get("UPDATE_GOLDEN") or not path.exists():
        GOLDEN_DIR.mkdir(exist_ok=True)
        image.save(str(path))
        pytest.skip(f"еталон {path.name} створено — перевірте його вручну")
    golden = QImage(str(path))
    mean, strong = difference(image, golden)
    if mean > mean_tol or strong > strong_tol:
        failed = path.with_name(f"{name}.actual.png")
        image.save(str(failed))
        pytest.fail(f"Відмальовування відрізняється від еталону: середня різниця {mean:.2f}, "
                    f"сильно відмінних пікселів {strong:.2%}. Фактичне: {failed}")
