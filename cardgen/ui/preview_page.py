"""Попередній перегляд карток усіх товарів з можливістю поправити окрему картку."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListView,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..model.walk import iter_elements
from ..products import Products
from ..storage import StorageError, Workspace
from . import dialogs, export_dialog
from .editor.page import EditorPage

THUMB = 110
PROBLEM_COLOR = QColor("#E5484D")
OVERRIDE_COLOR = QColor("#1E5BFF")


class PreviewPage(QWidget):
    back = Signal()

    def __init__(self, workspace: Workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self.products: Products | None = None
        self.current = -1

        back = QPushButton("← Назад")
        back.setObjectName("btn_back")
        back.clicked.connect(self.leave)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.prev_button = QPushButton("◀")
        self.prev_button.setToolTip("Попередній товар (Page Up)")
        self.prev_button.clicked.connect(lambda: self.go(self.current - 1))
        self.next_button = QPushButton("▶")
        self.next_button.setToolTip("Наступний товар (Page Down)")
        self.next_button.clicked.connect(lambda: self.go(self.current + 1))
        self.prev_button.setShortcut("PgUp")
        self.next_button.setShortcut("PgDown")
        self.save_product_button = QPushButton("Зберегти для товару")
        self.save_product_button.setObjectName("btn_save_product")
        self.save_product_button.setToolTip("Правки лише для цієї картки. Зберігаються й після "
                                            "повторного завантаження таблиці.")
        self.save_product_button.clicked.connect(self.save_for_product)
        self.save_template_button = QPushButton("Зберегти для шаблону")
        self.save_template_button.setObjectName("btn_save_template")
        self.save_template_button.setToolTip("Внести зміни в шаблон — для всіх товарів. "
                                             "Підставлені з таблиці тексти й фото лишаються правкою цього товару.")
        self.save_template_button.clicked.connect(self.save_for_template)
        self.reset_button = QPushButton("Скинути правки товару")
        self.reset_button.setObjectName("btn_reset")
        self.reset_button.clicked.connect(self.reset_product)
        self.export_button = QPushButton("Експорт JPEG…")
        self.export_button.setObjectName("btn_export_jpeg")
        self.export_button.clicked.connect(self.export_jpeg)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addWidget(self.title)
        top.addStretch()
        for w in (self.prev_button, self.next_button, self.save_product_button,
                  self.save_template_button, self.reset_button, self.export_button):
            top.addWidget(w)

        self.problems = QLabel()
        self.problems.setObjectName("problems")
        self.problems.setWordWrap(True)

        self.editor = EditorPage(workspace, preview=True)
        self.editor.changed.connect(self._update_buttons)

        self.summary = QLabel()
        self.summary.setObjectName("stripSummary")
        self.strip = QListWidget()
        self.strip.setObjectName("productStrip")
        self.strip.setViewMode(QListView.ViewMode.IconMode)
        self.strip.setFlow(QListView.Flow.LeftToRight)
        self.strip.setWrapping(False)
        self.strip.setMovement(QListView.Movement.Static)
        self.strip.setIconSize(QSize(THUMB, THUMB))
        self.strip.setGridSize(QSize(THUMB + 24, THUMB + 40))
        self.strip.setFixedHeight(THUMB + 64)
        self.strip.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.strip.currentRowChanged.connect(self._strip_clicked)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.problems)
        layout.addWidget(self.editor, 1)
        layout.addWidget(self.summary)
        layout.addWidget(self.strip)

    # --- Відкриття ----------------------------------------------------------------

    def open(self, category_id: str, template_id: str, index: int = 0) -> None:
        self.products = Products(self.workspace, category_id, template_id)
        self.title.setText(f"Перегляд: {self.products.template.name}")
        self.current = -1
        self.rebuild_strip()
        if len(self.products):
            self.go(min(index, len(self.products) - 1), ask=False)
        else:
            self.problems.setText("Даних ще немає — заповніть «Дані товарів».")
            self._update_buttons()

    def rebuild_strip(self) -> None:
        self.strip.blockSignals(True)
        self.strip.clear()
        for i in range(len(self.products)):
            item = QListWidgetItem()
            self.strip.addItem(item)
            self.update_thumb(i)
            if i % 10 == 9:
                QApplication.processEvents()  # не «замерзати» на сотні товарів
        self.strip.blockSignals(False)
        self._update_summary()

    def product_problems(self, index: int, overflow: set[str]) -> list[str]:
        problems = [f"{i.column}: {i.message}" if i.column else i.message
                    for i in self.products.row_issues(index) if i.level == "error"]
        if overflow:
            names = {e.id: e.name or e.TYPE for e in iter_elements(self.products.template.elements)}
            blocks = sorted({names.get(key.split(":")[0], key) for key in overflow})
            problems.append("Текст не вміщується: " + ", ".join(blocks))
        return problems

    def update_thumb(self, index: int) -> None:
        p = self.products
        scale = THUMB / max(p.template.width, p.template.height)
        rendered = p.render(index, scale)
        problems = self.product_problems(index, rendered.overflow)
        pixmap = QPixmap(THUMB, THUMB)
        pixmap.fill(QColor("#E9ECF2"))
        painter = QPainter(pixmap)
        x = (THUMB - rendered.image.width()) / 2
        y = (THUMB - rendered.image.height()) / 2
        painter.drawImage(int(x), int(y), rendered.image)
        if problems:
            painter.setPen(QPen(PROBLEM_COLOR, 4))
            painter.drawRect(2, 2, THUMB - 4, THUMB - 4)
        painter.end()
        item = self.strip.item(index)
        marks = ("⚠ " if problems else "") + ("✎ " if p.has_override(index) else "")
        item.setIcon(QIcon(pixmap))
        item.setText(marks + p.article(index))
        item.setToolTip("\n".join(problems) if problems else "Без проблем")
        item.setData(Qt.ItemDataRole.UserRole, problems)

    def _update_summary(self) -> None:
        p = self.products
        problems = sum(1 for i in range(self.strip.count()) if self.strip.item(i).data(Qt.ItemDataRole.UserRole))
        overrides = sum(1 for i in range(len(p)) if p.has_override(i))
        text = f"Карток: {len(p)}"
        text += f" · з проблемами: {problems} (⚠)" if problems else " · проблем немає"
        if overrides:
            text += f" · з ручними правками: {overrides} (✎)"
        self.summary.setText(text)

    # --- Перехід між товарами ---------------------------------------------------------

    def go(self, index: int, ask: bool = True) -> bool:
        if self.products is None or not 0 <= index < len(self.products):
            return False
        if ask and self.editor.dirty and index != self.current:
            if dialogs.confirm(self, "Незбережені правки",
                               f"Картку «{self.products.article(self.current)}» змінено. "
                               "Зберегти правки для цього товару?"):
                self.save_for_product()
        self.current = index
        p = self.products
        self.editor.open_card(p.category_id, p.card(index), p.images,
                              f"{p.article(index)}  ({index + 1} з {len(p)})")
        problems = self.strip.item(index).data(Qt.ItemDataRole.UserRole) or []
        self.problems.setText("⚠ " + " · ".join(problems) if problems else "")
        self.problems.setStyleSheet("color: #F04438;" if problems else "")
        self.strip.blockSignals(True)
        self.strip.setCurrentRow(index)
        self.strip.blockSignals(False)
        self._update_buttons()
        return True

    def _strip_clicked(self, row: int) -> None:
        if row != self.current and row >= 0:
            if not self.go(row):
                return

    def _update_buttons(self) -> None:
        has = self.products is not None and 0 <= self.current < len(self.products)
        self.prev_button.setEnabled(has and self.current > 0)
        self.next_button.setEnabled(has and self.current < len(self.products) - 1)
        self.save_product_button.setEnabled(has and self.editor.dirty)
        self.save_template_button.setEnabled(has and self.editor.dirty)
        self.reset_button.setEnabled(has and self.products.has_override(self.current))

    # --- Збереження ---------------------------------------------------------------------

    def save_for_product(self) -> None:
        if not self._valid():
            return
        try:
            self.products.save_for_product(self.current, self.editor.template)
        except (StorageError, OSError) as e:
            dialogs.error(self, f"Не вдалося зберегти правки: {e}")
            return
        self._after_save([self.current])

    def save_for_template(self) -> None:
        if not self._valid():
            return
        if not dialogs.confirm(self, "Зберегти для шаблону",
                               "Внести ці зміни в шаблон для всіх товарів?\n\nТексти й фото, "
                               "підставлені з таблиці, лишаться правкою лише цього товару."):
            return
        try:
            self.products.save_for_template(self.current, self.editor.template)
        except (StorageError, OSError) as e:
            dialogs.error(self, f"Не вдалося зберегти шаблон: {e}")
            return
        self._after_save(range(len(self.products)))

    def reset_product(self) -> None:
        if not self._valid():
            return
        if dialogs.confirm(self, "Скинути правки",
                           f"Прибрати всі ручні правки картки «{self.products.article(self.current)}»?"):
            self.products.reset(self.current)
            self._after_save([self.current])

    def _valid(self) -> bool:
        return self.products is not None and 0 <= self.current < len(self.products)

    def _after_save(self, indexes) -> None:
        for i in indexes:
            self.update_thumb(i)
        self._update_summary()
        self.editor.dirty = False
        self.go(self.current, ask=False)

    def export_jpeg(self) -> None:
        if self.products is None:
            return
        if self.editor.dirty and self._valid() and dialogs.confirm(
                self, "Незбережені правки", "Зберегти правки поточної картки перед експортом?"):
            self.save_for_product()
        export_dialog.ask_export(self, self.workspace, self.products.category_id, [self.products.template_id])

    def leave(self) -> None:
        if self.editor.dirty and self._valid() and dialogs.confirm(
                self, "Незбережені правки", "Зберегти правки поточної картки для цього товару?"):
            self.save_for_product()
        self.editor.dirty = False
        self.back.emit()
