import os
import sys
from pathlib import Path

import pytest

# вікна не з'являються на екрані під час тестів
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# без цього offscreen-режим не бачить системних шрифтів і малює квадрати
os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cardgen.model import (  # noqa: E402
    Background,
    FieldBinding,
    GroupElement,
    IconElement,
    Paint,
    PhotoElement,
    Shadow,
    ShapeElement,
    TableElement,
    Template,
    TextElement,
    TextStyle,
)
from cardgen.storage import Workspace  # noqa: E402


@pytest.fixture
def workspace(tmp_path) -> Workspace:
    return Workspace(tmp_path / "ws")


@pytest.fixture
def full_template() -> Template:
    """Шаблон з усіма типами блоків і нестандартними значеннями."""
    table = TableElement.create(3, 2, x=40, y=500, width=600, height=300)
    table.cells[0][0].text = "Переріз"
    table.cells[0][1].binding = FieldBinding(enabled=True, column="Переріз", suffix=" AWG")
    table.cells[1][1].background = Paint(kind="solid", color="#EEF3FF")

    title = TextElement(
        name="Заголовок",
        x=40, y=40, width=600, height=120,
        text="Кабель силіконовий",
        style=TextStyle(font_family="Manrope", font_size=64, bold=True, color="#0B1F44"),
        auto_shrink=True, min_font_size=24,
    )
    badge_bg = ShapeElement(
        x=40, y=180, width=500, height=60, corner_radius=14,
        fill=Paint(kind="linear", color="#FFD54A", color2="#FFB300", angle=45),
        shadow=Shadow(enabled=True, blur=20),
    )
    badge_text = TextElement(
        x=60, y=190, width=460, height=40, text="",
        binding=FieldBinding(enabled=True, column="Довжина", field_type="number",
                             prefix="Довжина: ", suffix=" м", required=True),
    )
    return Template(
        name="Обкладинка",
        width=1200, height=1200,
        background=Background(asset="library:backgrounds/circuit.png", scale=1.3),
        elements=[
            title,
            GroupElement(name="Плашка", children=[badge_bg, badge_text]),
            PhotoElement(x=600, y=200, width=550, height=550, rotation=-12, content_scale=1.4),
            IconElement(x=40, y=900, width=64, height=64, asset="library:icons/rocket.svg",
                        tint="#1E5BFF", locked=True),
            table,
        ],
    )
