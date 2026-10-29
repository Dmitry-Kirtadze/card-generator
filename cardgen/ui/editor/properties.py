"""Панель властивостей вибраного блоку або полотна (коли нічого не вибрано)."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...model import (
    Element,
    GroupElement,
    IconElement,
    PhotoElement,
    ShapeElement,
    TableElement,
    Template,
    TextElement,
)
from ...data.fields import KEY_COLUMN, build_schema
from ...storage import StorageError, Workspace
from .. import dialogs
from ..color_button import ColorButton
from .asset_picker import pick_asset
from .table_panel import build_table

TYPE_TITLES = {
    "text": "Текст", "shape": "Фігура", "icon": "Іконка", "photo": "Фото",
    "table": "Таблиця", "group": "Група",
}
SHAPE_TITLES = {"rect": "Прямокутник", "ellipse": "Коло / еліпс", "line": "Лінія"}


class PropertiesPanel(QWidget):
    """changed(obj) — змінено блок або шаблон (obj — Element чи Template)."""

    changed = Signal(object, str)  # об'єкт, ключ поля (для злиття дій в історії)
    actionRequested = Signal(str)  # align_left, distribute_h, group, ungroup …
    cellsSelected = Signal(set)  # вибрані клітинки таблиці {(рядок, стовпець)}

    def __init__(self, workspace: Workspace, parent=None, *, preview: bool = False):
        super().__init__(parent)
        self.preview = preview  # картка товару: без налаштувань полотна й заповнюваних полів
        self.workspace = workspace
        self.category_id: str | None = None
        self.template: Template | None = None
        self.target: Element | Template | None = None
        self._refreshers: list[Callable[[], None]] = []
        self._updating = False
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.addStretch(1)
        self._body: QWidget | None = None
        self.table_cells: set[tuple[int, int]] = set()

    # --- Побудова -----------------------------------------------------------

    def select_cells(self, cells: set[tuple[int, int]]) -> None:
        """Вибрати клітинки поточної таблиці (з полотна або кнопкою «всі»)."""
        self.table_cells = set(cells)
        self.cellsSelected.emit(self.table_cells)
        if isinstance(self.target, TableElement):
            self.set_target(self.target)

    def set_target(self, target: Element | Template | list | None) -> None:
        if target is not self.target:
            self.table_cells = set()
        self.target = target
        self._refreshers = []
        if self._body is not None:
            # прибрати одразу: deleteLater спрацює лише в наступному циклі подій
            self._layout.removeWidget(self._body)
            self._body.hide()
            self._body.deleteLater()
        self._body = QWidget()
        self._form = QFormLayout(self._body)
        self._form.setContentsMargins(0, 0, 0, 0)
        if isinstance(target, Template) and self.preview:
            note = QLabel("Виберіть блок на картці, щоб змінити його для цього товару.\n\n"
                          "Розмір полотна й фон змінюються в редакторі шаблону.")
            note.setWordWrap(True)
            note.setStyleSheet("color: #6B7280;")
            self._form.addRow(note)
        elif isinstance(target, Template):
            self._build_template(target)
        elif isinstance(target, GroupElement):
            self._build_group(target)
        elif isinstance(target, Element):
            self._build_element(target)
        elif isinstance(target, list):
            self._build_multi(target)
        self._layout.insertWidget(0, self._body)
        self._body.show()  # інакше Qt покаже його лише в наступному циклі подій
        self.refresh()

    def refresh(self) -> None:
        """Оновити значення полів з моделі (наприклад, після перетягування на полотні)."""
        self._updating = True
        try:
            for refresh in self._refreshers:
                refresh()
        finally:
            self._updating = False

    def _emit(self, field: str) -> None:
        if not self._updating:
            owner = getattr(self.target, "id", "template")
            self.changed.emit(self.target, f"{owner}:{field}")

    def _section(self, title: str) -> None:
        label = QLabel(title)
        label.setStyleSheet("font-weight: 600; padding-top: 10px;")
        self._form.addRow(label)

    # --- Поля, прив'язані до атрибутів ------------------------------------

    def number(self, label: str, obj: Any, attr: str, lo: float, hi: float, *,
               step: float = 1, decimals: int = 0, suffix: str = "", key: str | None = None) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setObjectName(key or attr)
        spin.setRange(lo, hi)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)

        def apply(value: float) -> None:
            if not self._updating:
                setattr(obj, attr, int(value) if isinstance(getattr(obj, attr), int) else value)
                self._emit(key or attr)

        spin.valueChanged.connect(apply)
        self._refreshers.append(lambda: spin.setValue(getattr(obj, attr)))
        self._form.addRow(label, spin)
        return spin

    def check(self, label: str, obj: Any, attr: str, key: str | None = None) -> QCheckBox:
        box = QCheckBox(label)
        box.setObjectName(key or attr)

        def apply(state: bool) -> None:
            if not self._updating:
                setattr(obj, attr, state)
                self._emit(key or attr)

        box.toggled.connect(apply)
        self._refreshers.append(lambda: box.setChecked(getattr(obj, attr)))
        self._form.addRow(box)
        return box

    def combo(self, label: str, obj: Any, attr: str, options: list[tuple[str, str]],
              key: str | None = None, on_change: Callable[[], None] | None = None) -> QComboBox:
        box = QComboBox()
        box.setObjectName(key or attr)
        for value, title in options:
            box.addItem(title, value)

        def apply(_index: int) -> None:
            if not self._updating:
                setattr(obj, attr, box.currentData())
                self._emit(key or attr)
                if on_change:
                    on_change()

        box.currentIndexChanged.connect(apply)
        self._refreshers.append(lambda: box.setCurrentIndex(max(0, box.findData(getattr(obj, attr)))))
        self._form.addRow(label, box)
        return box

    def color(self, label: str, obj: Any, attr: str, *, allow_none: bool = False,
              key: str | None = None) -> ColorButton:
        button = ColorButton(self.workspace.recent_colors, self.workspace.add_recent_color,
                             allow_none=allow_none)
        button.setObjectName(key or attr)

        def apply(value: str) -> None:
            setattr(obj, attr, value)
            self._emit(key or attr)

        button.colorChanged.connect(apply)
        self._refreshers.append(lambda: button.set_color(getattr(obj, attr)))
        self._form.addRow(label, button)
        return button

    def line(self, label: str, obj: Any, attr: str, key: str | None = None) -> QLineEdit:
        edit = QLineEdit()
        edit.setObjectName(key or attr)

        def apply(value: str) -> None:
            if not self._updating:
                setattr(obj, attr, value)
                self._emit(key or attr)

        edit.textEdited.connect(apply)
        self._refreshers.append(lambda: edit.setText(getattr(obj, attr)))
        self._form.addRow(label, edit)
        return edit

    def multiline(self, label: str, obj: Any, attr: str, key: str | None = None) -> QPlainTextEdit:
        edit = QPlainTextEdit()
        edit.setObjectName(key or attr)
        edit.setFixedHeight(90)

        def apply() -> None:
            if not self._updating and edit.toPlainText() != getattr(obj, attr):
                setattr(obj, attr, edit.toPlainText())
                self._emit(key or attr)

        def refresh() -> None:
            if edit.toPlainText() != getattr(obj, attr):
                edit.setPlainText(getattr(obj, attr))

        edit.textChanged.connect(apply)
        self._refreshers.append(refresh)
        self._form.addRow(label, edit)
        return edit

    def font(self, label: str, obj: Any, attr: str) -> QFontComboBox:
        box = QFontComboBox()
        box.setObjectName(attr)

        def apply(font: QFont) -> None:
            if not self._updating:
                setattr(obj, attr, font.family())
                self._emit(attr)

        box.currentFontChanged.connect(apply)
        self._refreshers.append(lambda: box.setCurrentFont(QFont(getattr(obj, attr))))
        self._form.addRow(label, box)
        return box

    def button(self, text: str, handler: Callable[[], None], key: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(key)
        button.clicked.connect(handler)
        self._form.addRow(button)
        return button

    # --- Заповнюване поле ---------------------------------------------------

    def known_columns(self) -> list[str]:
        if self.template is None:
            return []
        return [c for c in build_schema(self.template).columns if c != KEY_COLUMN]

    def binding_section(self, binding: Any, *, image: bool = False, key: str = "bind",
                        rebuild: Callable[[], None] | None = None) -> None:
        """Галочка «Заповнюване» і, якщо вона стоїть, — налаштування поля таблиці даних."""
        if self.preview:
            return  # у картці товару дані вже підставлені
        self._section("Заповнюване поле")
        enabled = QCheckBox("Брати фото з таблиці даних" if image else "Брати текст з таблиці даних")
        enabled.setObjectName(f"{key}_enabled")

        def toggle(state: bool) -> None:
            if self._updating:
                return
            binding.enabled = state
            if state and not binding.column.strip():
                binding.column = "Фото" if image else ""
            binding.field_type = "image" if image else (binding.field_type if binding.field_type != "image"
                                                         else "text")
            self._emit(f"{key}_enabled")
            if rebuild:
                rebuild()

        enabled.toggled.connect(toggle)
        self._refreshers.append(lambda: enabled.setChecked(binding.enabled))
        self._form.addRow(enabled)
        if not binding.enabled:
            return

        column = QComboBox()
        column.setObjectName(f"{key}_column")
        column.setEditable(True)
        column.addItems(self.known_columns())
        column.lineEdit().setPlaceholderText("Назва стовпця, напр. Переріз")

        def set_column(text: str) -> None:
            if not self._updating and text.strip() != binding.column:
                binding.column = text.strip()
                self._emit(f"{key}_column")

        column.editTextChanged.connect(set_column)
        self._refreshers.append(lambda: column.setEditText(binding.column))
        self._form.addRow("Стовпець", column)

        if not image:
            self.combo("Тип даних", binding, "field_type",
                       [("text", "Текст"), ("number", "Число"), ("list", "Вибір зі списку")],
                       key=f"{key}_type", on_change=rebuild)
            if binding.field_type == "list":
                options = QLineEdit()
                options.setObjectName(f"{key}_options")
                options.setPlaceholderText("червоний, чорний, синій")

                def set_options(text: str) -> None:
                    if not self._updating:
                        binding.options = [o.strip() for o in text.split(",") if o.strip()]
                        self._emit(f"{key}_options")

                options.textEdited.connect(set_options)
                self._refreshers.append(lambda: options.setText(", ".join(binding.options)))
                self._form.addRow("Варіанти", options)
            self.line("Префікс", binding, "prefix", key=f"{key}_prefix")
            self.line("Суфікс", binding, "suffix", key=f"{key}_suffix")
        self.check("Обов'язкове", binding, "required", key=f"{key}_required")
        hint = QLabel("Стовпець з'явиться в таблиці даних. Однакова назва в кількох блоках — "
                      "одне значення для всіх.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6B7280;")
        self._form.addRow(hint)

    # --- Полотно -----------------------------------------------------------

    def _build_template(self, t: Template) -> None:
        self._section("Полотно")
        self.number("Ширина", t, "width", 100, 6000, suffix=" px")
        self.number("Висота", t, "height", 100, 6000, suffix=" px")
        self._section("Фон")
        bg = t.background
        self.color("Колір", bg, "color", key="bg_color")
        self._asset_label = QLabel()
        self._refreshers.append(lambda: self._asset_label.setText(bg.asset.split("/")[-1] or "немає"))
        self._form.addRow("Зображення", self._asset_label)
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        choose = QPushButton("Вибрати…")
        choose.setObjectName("bg_choose")
        choose.clicked.connect(lambda: self._pick_background(bg))
        clear = QPushButton("Прибрати")
        clear.setObjectName("bg_clear")
        clear.clicked.connect(lambda: self._set_and_emit(bg, "asset", ""))
        row_layout.addWidget(choose)
        row_layout.addWidget(clear)
        self._form.addRow(row)
        self.combo("Вписування", bg, "fit", [("cover", "Заповнити"), ("contain", "Вписати"),
                                             ("stretch", "Розтягнути")], key="bg_fit")
        self.number("Масштаб", bg, "scale", 0.1, 10, step=0.05, decimals=2, key="bg_scale")
        self.number("Зсув X", bg, "offset_x", -10000, 10000, key="bg_offset_x")
        self.number("Зсув Y", bg, "offset_y", -10000, 10000, key="bg_offset_y")
        hint = QLabel("Фон не реагує на мишу — блоки поверх нього можна вільно рухати.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6B7280;")
        self._form.addRow(hint)

    def _pick_background(self, bg) -> None:
        ref = pick_asset(self, self.workspace, "backgrounds")
        if ref:
            self._set_and_emit(bg, "asset", ref)

    def _set_and_emit(self, obj: Any, attr: str, value: Any) -> None:
        setattr(obj, attr, value)
        self.refresh()
        self._emit(attr)

    # --- Блоки -------------------------------------------------------------

    def _build_element(self, e: Element) -> None:
        title = TYPE_TITLES.get(e.TYPE, e.TYPE)
        if isinstance(e, ShapeElement):
            title = SHAPE_TITLES.get(e.shape, title)
        header = QLabel(title)
        header.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self._form.addRow(header)
        self.line("Назва", e, "name")

        self._section("Розташування")
        self.number("X", e, "x", -20000, 20000, decimals=0)
        self.number("Y", e, "y", -20000, 20000, decimals=0)
        self.number("Ширина", e, "width", 1, 20000)
        self.number("Висота", e, "height", 1, 20000)
        self.number("Поворот", e, "rotation", -360, 360, suffix="°")
        self._opacity(e)
        self.check("Заблокувати", e, "locked")
        self._align_section("Вирівняти на полотні", distribute=False)

        if isinstance(e, TextElement):
            self._build_text(e)
        elif isinstance(e, ShapeElement):
            self._build_shape(e)
        elif isinstance(e, IconElement):
            self._build_icon(e)
        elif isinstance(e, PhotoElement):
            self._build_photo(e)
        elif isinstance(e, TableElement):
            build_table(self, e)

    # --- Група і кілька блоків ----------------------------------------------

    def _build_group(self, g: GroupElement) -> None:
        header = QLabel(f"Група · {len(g.children)} бл.")
        header.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self._form.addRow(header)
        self.line("Назва", g, "name")
        hint = QLabel("Клік по блоку групи виділяє всю групу. Подвійний клік — окремий блок.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6B7280;")
        self._form.addRow(hint)
        self._opacity(g)
        self.check("Заблокувати", g, "locked")
        self.button("Розгрупувати", lambda: self.actionRequested.emit("ungroup"), "btn_ungroup")
        self._align_section("Вирівняти на полотні", distribute=False)

    def _build_multi(self, elements: list) -> None:
        header = QLabel(f"Вибрано блоків: {len(elements)}")
        header.setStyleSheet("font-size: 13pt; font-weight: 600;")
        self._form.addRow(header)
        self.button("Згрупувати", lambda: self.actionRequested.emit("group"), "btn_group")
        self._align_section("Вирівняти між собою", distribute=len(elements) >= 3)

    def _align_section(self, title: str, distribute: bool) -> None:
        self._section(title)
        grid = QWidget()
        layout = QGridLayout(grid)
        layout.setContentsMargins(0, 0, 0, 0)
        actions = [
            ("align_left", "Ліворуч"), ("align_hcenter", "По центру"), ("align_right", "Праворуч"),
            ("align_top", "Зверху"), ("align_vcenter", "Посередині"), ("align_bottom", "Знизу"),
        ]
        if distribute:
            actions += [("distribute_h", "Рівно по ширині"), ("distribute_v", "Рівно по висоті")]
        for i, (key, text) in enumerate(actions):
            button = QPushButton(text)
            button.setObjectName(f"btn_{key}")
            button.clicked.connect(lambda _=False, k=key: self.actionRequested.emit(k))
            layout.addWidget(button, i // 3, i % 3)
        self._form.addRow(grid)

    def _opacity(self, e: Element) -> None:
        spin = QSpinBox()
        spin.setObjectName("opacity")
        spin.setRange(0, 100)
        spin.setSuffix(" %")
        spin.setKeyboardTracking(False)

        def apply(value: int) -> None:
            if not self._updating:
                e.opacity = value / 100
                self._emit("opacity")

        spin.valueChanged.connect(apply)
        self._refreshers.append(lambda: spin.setValue(round(e.opacity * 100)))
        self._form.addRow("Прозорість", spin)

    def _build_text(self, e: TextElement) -> None:
        self.binding_section(e.binding, rebuild=lambda: self.set_target(e))
        self._section("Текст")
        self.multiline("Приклад тексту" if e.binding.enabled else "Текст", e, "text")
        s = e.style
        self.font("Шрифт", s, "font_family")
        self.number("Розмір", s, "font_size", 1, 1000, suffix=" px")
        self.check("Жирний", s, "bold")
        self.check("Курсив", s, "italic")
        self.color("Колір", s, "color", key="text_color")
        self.combo("Вирівнювання", s, "align", [("left", "Ліворуч"), ("center", "По центру"),
                                                ("right", "Праворуч")])
        self.combo("По вертикалі", s, "valign", [("top", "Зверху"), ("middle", "Посередині"),
                                                 ("bottom", "Знизу")])
        self.number("Міжрядковий", s, "line_height", 0.5, 4, step=0.05, decimals=2)
        self.number("Між літерами", s, "letter_spacing", -20, 100, step=0.5, decimals=1, suffix=" px")
        self._section("Якщо не вміщується")
        self.check("Переносити рядки", e, "wrap")
        self.check("Зменшувати шрифт", e, "auto_shrink")
        self.number("Мінімальний розмір", e, "min_font_size", 1, 500, suffix=" px")

    def _build_shape(self, e: ShapeElement) -> None:
        if e.shape == "line":
            self._section("Лінія")
            self.color("Колір", e.stroke, "color", key="stroke_color")
            self.number("Товщина", e.stroke, "width", 0.5, 200, step=0.5, decimals=1, key="stroke_width")
            caps = QCheckBox("Заокруглені кінці")
            caps.setObjectName("line_caps")

            def apply_caps(state: bool) -> None:
                if not self._updating:
                    e.corner_radius = 1.0 if state else 0.0
                    self._emit("line_caps")

            caps.toggled.connect(apply_caps)
            self._refreshers.append(lambda: caps.setChecked(e.corner_radius > 0))
            self._form.addRow(caps)
        else:
            self._section("Заливка")
            self.combo("Тип", e.fill, "kind", [("solid", "Колір"), ("linear", "Градієнт"),
                                               ("none", "Без заливки")], key="fill_kind",
                       on_change=lambda: self.set_target(e))
            if e.fill.kind != "none":
                self.color("Колір" if e.fill.kind == "solid" else "Колір 1", e.fill, "color",
                           key="fill_color")
            if e.fill.kind == "linear":
                self.color("Колір 2", e.fill, "color2", key="fill_color2")
                self.number("Кут", e.fill, "angle", -360, 360, suffix="°", key="fill_angle")
            if e.shape == "rect":
                self.number("Скруглення", e, "corner_radius", 0, 5000, suffix=" px")
            self._section("Обведення")
            self.color("Колір", e.stroke, "color", key="stroke_color")
            self.number("Товщина", e.stroke, "width", 0, 200, step=0.5, decimals=1, key="stroke_width")
        self._shadow(e.shadow, e)

    def _shadow(self, shadow, owner: Element) -> None:
        self._section("Тінь")
        self.check("Тінь", shadow, "enabled", key="shadow_enabled")
        self.color("Колір", shadow, "color", key="shadow_color")
        self.number("Розмиття", shadow, "blur", 0, 300, key="shadow_blur")
        self.number("Зсув X", shadow, "offset_x", -500, 500, key="shadow_x")
        self.number("Зсув Y", shadow, "offset_y", -500, 500, key="shadow_y")

    def _build_icon(self, e: IconElement) -> None:
        self._section("Іконка")
        label = QLabel()
        self._refreshers.append(lambda: label.setText(e.asset.split("/")[-1] or "не вибрано"))
        self._form.addRow("Файл", label)
        self.button("Змінити іконку…", lambda: self._pick_icon(e), "icon_choose")
        self.color("Перефарбувати", e, "tint", allow_none=True, key="icon_tint")

    def _pick_icon(self, e: IconElement) -> None:
        ref = pick_asset(self, self.workspace, "icons")
        if ref:
            self._set_and_emit(e, "asset", ref)

    def _build_photo(self, e: PhotoElement) -> None:
        self.binding_section(e.binding, image=True, rebuild=lambda: self.set_target(e))
        self._section("Фото")
        note = QLabel("Зразок потрібен лише для редактора — щоб бачити, як виглядатиме картка. "
                      "Якщо фото не заповнюване, зразок і буде фото на всіх картках.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #6B7280;")
        self._form.addRow(note)
        label = QLabel()
        self._refreshers.append(lambda: label.setText(e.placeholder.split("/")[-1] or "немає"))
        self._form.addRow("Зразок", label)
        self.button("Вибрати фото-зразок…", lambda: self._pick_placeholder(e), "photo_choose")
        self.combo("Вписування", e, "fit", [("contain", "Вписати"), ("cover", "Заповнити"),
                                            ("stretch", "Розтягнути")])
        self.number("Масштаб фото", e, "content_scale", 0.05, 20, step=0.05, decimals=2)
        self.number("Зсув фото X", e, "content_offset_x", -10000, 10000)
        self.number("Зсув фото Y", e, "content_offset_y", -10000, 10000)
        self.number("Скруглення", e, "corner_radius", 0, 5000, suffix=" px")
        self._section("Білий фон")
        self.check("Прибрати білий фон", e, "remove_white")
        self.number("Чутливість", e, "white_tolerance", 1, 80)
        note = QLabel("Білий фон навколо товару стає прозорим. Більша чутливість прибирає й світло-сірі "
                      "тіні, але може зачепити світлі частини товару. Тінь рамки при цьому не малюється.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #6B7280;")
        self._form.addRow(note)
        self._shadow(e.shadow, e)

    def _pick_placeholder(self, e: PhotoElement) -> None:
        path = dialogs.open_file(self, "Фото-зразок", "Зображення (*.png *.jpg *.jpeg *.webp)")
        if path is None or self.category_id is None:
            return
        try:
            ref = self.workspace.add_category_asset(self.category_id, path)
        except (StorageError, OSError) as err:
            dialogs.error(self, str(err))
            return
        self._set_and_emit(e, "placeholder", ref)
