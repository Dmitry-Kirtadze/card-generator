"""Розкладка тексту в рамці: перенесення слів і автоматичне зменшення шрифту.

Розміри шрифту — у пікселях полотна, тому результат однаковий у редакторі
(з будь-яким масштабом) та в експорті.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QFont, QFontMetricsF, QPainter

from ..model import TextStyle
from .colors import qcolor

EPS = 0.5


@dataclass
class TextLayout:
    font: QFont
    font_size: int
    lines: list[str]
    line_step: float
    width: float
    height: float
    overflow: bool


def make_font(style: TextStyle, size: float) -> QFont:
    font = QFont(style.font_family)
    font.setPixelSize(max(1, round(size)))
    font.setBold(style.bold)
    font.setItalic(style.italic)
    font.setKerning(True)
    # без хінтингу ширина тексту не залежить від масштабу -> редактор = експорт
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    if style.letter_spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, style.letter_spacing)
    return font


def wrap_lines(text: str, fm: QFontMetricsF, width: float, wrap: bool) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not wrap:
            lines.append(paragraph)
            continue
        current = ""
        for word in paragraph.split(" "):
            candidate = word if not current else f"{current} {word}"
            if fm.horizontalAdvance(candidate) <= width + EPS:
                current = candidate
                continue
            if current:
                lines.append(current)
            # слово довше за рядок — ріжемо по літерах
            while fm.horizontalAdvance(word) > width + EPS and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and fm.horizontalAdvance(word[:cut]) > width + EPS:
                    cut -= 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def _attempt(text: str, style: TextStyle, size: int, width: float, wrap: bool) -> TextLayout:
    font = make_font(style, size)
    fm = QFontMetricsF(font)
    lines = wrap_lines(text, fm, width, wrap)
    step = size * style.line_height
    text_w = max((fm.horizontalAdvance(line) for line in lines), default=0.0)
    return TextLayout(font, size, lines, step, text_w, step * len(lines), False)


def _fits(layout: TextLayout, width: float, height: float) -> bool:
    return layout.height <= height + EPS and layout.width <= width + EPS


def layout_text(text: str, style: TextStyle, width: float, height: float, *,
                wrap: bool = True, auto_shrink: bool = True,
                min_font_size: float = 10) -> TextLayout:
    size = max(1, round(style.font_size))
    layout = _attempt(text, style, size, width, wrap)
    if _fits(layout, width, height):
        return layout
    if auto_shrink:
        low, high = max(1, round(min(min_font_size, size))), size - 1
        best = None
        while low <= high:  # найбільший розмір, що вміщується
            mid = (low + high) // 2
            candidate = _attempt(text, style, mid, width, wrap)
            if _fits(candidate, width, height):
                best, low = candidate, mid + 1
            else:
                high = mid - 1
        if best is not None:
            return best
        layout = _attempt(text, style, max(1, round(min(min_font_size, size))), width, wrap)
    layout.overflow = True
    return layout


def draw_text(painter: QPainter, rect: QRectF, layout: TextLayout, style: TextStyle) -> None:
    painter.setFont(layout.font)
    painter.setPen(qcolor(style.color, "#111111"))
    fm = QFontMetricsF(layout.font)
    if style.valign == "middle":
        top = rect.top() + (rect.height() - layout.height) / 2
    elif style.valign == "bottom":
        top = rect.bottom() - layout.height
    else:
        top = rect.top()
    glyph_h = fm.ascent() + fm.descent()
    for i, line in enumerate(layout.lines):
        line_w = fm.horizontalAdvance(line)
        if style.align == "center":
            x = rect.left() + (rect.width() - line_w) / 2
        elif style.align == "right":
            x = rect.right() - line_w
        else:
            x = rect.left()
        baseline = top + i * layout.line_step + (layout.line_step - glyph_h) / 2 + fm.ascent()
        painter.drawText(QPointF(x, baseline), line)
