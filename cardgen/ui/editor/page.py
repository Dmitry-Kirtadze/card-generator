"""Екран редактора шаблону.

Кожна дія користувача закінчується викликом commit(): знімок шаблону
потрапляє в історію (Undo/Redo), шаблон автоматично зберігається.

Виділення: на полотні є лише «листові» блоки, групи — логічні.
Клік по блоку групи виділяє всю групу; подвійний клік «заходить» у групу
і дозволяє вибрати окремий блок.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...model import (
    Element,
    GroupElement,
    IconElement,
    Paint,
    PhotoElement,
    ShapeElement,
    Stroke,
    TableElement,
    Template,
    TextElement,
    TextStyle,
)
from ...model import ops
from ...model.serialization import from_dict, template_from_dict, template_to_dict, to_dict
from ...render import RenderContext
from ...storage import StorageError, Workspace
from .. import dialogs
from .asset_picker import pick_asset
from .history import History
from .items import EditorScene, ElementItem
from .layers import LayersPanel
from .properties import PropertiesPanel
from .view import CanvasView

SAVE_DELAY_MS = 600
PASTE_OFFSET = 20
ZOOM_PRESETS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
NAME_PREFIX = {"text": "Текст", "rect": "Прямокутник", "ellipse": "Коло", "line": "Лінія",
               "icon": "Іконка", "photo": "Фото", "table": "Таблиця", "group": "Група"}

# буфер обміну блоків — спільний для всіх шаблонів у межах запуску програми
CLIPBOARD: list[dict] = []


def make_table(width: float, height: float, font_size: int) -> TableElement:
    """Нова таблиця «параметр — значення», як таблиця характеристик."""
    table = TableElement.create(5, 2, width=width, height=height,
                                border=Stroke(color="#E3E6EB", width=2))
    table.col_widths = [1.0, 1.2]
    for r, row in enumerate(table.cells):
        label, value = row
        label.text = f"Параметр {r + 1}"
        label.style.font_size = value.style.font_size = font_size
        label.style.color = "#374151"
        value.style.color = "#1E5BFF"
        value.style.bold = True
        label.padding = value.padding = 14
    return table


class EditorPage(QWidget):
    back = Signal()
    open_data = Signal(str, str)  # id категорії, id шаблону
    changed = Signal()  # режим перегляду: картку змінено
    open_preview = Signal(str, str)  # id категорії, id шаблону

    def __init__(self, workspace: Workspace, parent=None, *, preview: bool = False):
        """preview=True — редагування картки конкретного товару: не можна додавати/видаляти
        блоки й міняти шари, нічого не зберігається в шаблон автоматично
        (зберігає екран попереднього перегляду кнопками)."""
        super().__init__(parent)
        self.preview = preview
        self.data_images = None  # папка фото товарів для режиму перегляду
        self.workspace = workspace
        self.category_id: str | None = None
        self.template: Template | None = None
        self.scene: EditorScene | None = None
        self.ctx: RenderContext | None = None
        self.history = History()
        self._snapshot: dict = {}
        self.entered_group: str | None = None
        self._selecting = False
        self._paste_count = 0
        self.dirty = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self.save_now)

        self._build_ui()
        self._build_actions()

    # --- Інтерфейс ----------------------------------------------------------

    def _build_ui(self) -> None:
        back = QPushButton("← Шаблони")
        back.setObjectName("btn_back")
        back.clicked.connect(self.leave)
        self.title = QLabel()
        self.title.setObjectName("pageTitle")
        self.status = QLabel()
        self.status.setStyleSheet("color: #6B7280;")
        self.undo_button = QToolButton()
        self.undo_button.setText("↶ Скасувати")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button = QToolButton()
        self.redo_button.setText("↷ Повторити")
        self.redo_button.clicked.connect(self.redo)
        top = QHBoxLayout()
        top.addWidget(back)
        top.addWidget(self.title)
        top.addWidget(self.status)
        top.addStretch()
        top.addWidget(self.undo_button)
        top.addWidget(self.redo_button)

        tools = QHBoxLayout()
        self.add_buttons: dict[str, QPushButton] = {}
        for key, text in [("text", "Текст"), ("rect", "Прямокутник"), ("ellipse", "Коло"),
                          ("line", "Лінія"), ("icon", "Іконка"), ("photo", "Фото"), ("table", "Таблиця")]:
            button = QPushButton(f"+ {text}")
            button.setObjectName(f"add_{key}")
            button.clicked.connect(lambda _=False, k=key: self.add_block(k))
            tools.addWidget(button)
            self.add_buttons[key] = button
        tools.addSpacing(16)
        canvas_button = QPushButton("Полотно і фон")
        canvas_button.clicked.connect(self.select_canvas)
        tools.addWidget(canvas_button)
        data_button = QPushButton("Дані товарів")
        data_button.setObjectName("btn_data")
        data_button.setToolTip("Таблиця з даними для заповнюваних полів цього шаблону")
        data_button.clicked.connect(self._open_data)
        tools.addWidget(data_button)
        preview_button = QPushButton("Перегляд карток")
        preview_button.setObjectName("btn_preview")
        preview_button.clicked.connect(self._open_preview)
        tools.addWidget(preview_button)
        tools.addStretch()
        if self.preview:
            for widget in [back, canvas_button, data_button, preview_button, *self.add_buttons.values()]:
                widget.hide()

        settings = self.workspace.editor_settings()
        self.snap_box = QCheckBox("Прилипання")
        self.snap_box.setToolTip("Прилипання до країв, центру, інших блоків і сітки. Alt — тимчасово вимкнути.")
        self.snap_box.setChecked(settings.get("snap", True))
        self.snap_box.toggled.connect(self._grid_settings_changed)
        self.grid_box = QCheckBox("Сітка")
        self.grid_box.setChecked(settings.get("grid", False))
        self.grid_box.toggled.connect(self._grid_settings_changed)
        self.grid_size = QSpinBox()
        self.grid_size.setRange(5, 500)
        self.grid_size.setSuffix(" px")
        self.grid_size.setValue(int(settings.get("grid_size", 50)))
        self.grid_size.valueChanged.connect(self._grid_settings_changed)
        for w in (self.snap_box, self.grid_box, self.grid_size):
            tools.addWidget(w)
        tools.addSpacing(16)
        self.zoom_box = QComboBox()
        self.zoom_box.addItem("Вмістити", 0.0)
        for z in ZOOM_PRESETS:
            self.zoom_box.addItem(f"{round(z * 100)} %", z)
        self.zoom_box.activated.connect(self._zoom_selected)
        self.zoom_label = QLabel()
        tools.addWidget(QLabel("Масштаб:"))
        tools.addWidget(self.zoom_box)
        tools.addWidget(self.zoom_label)

        self.layers = LayersPanel()
        self.layers.selectionChangedIds.connect(self._layers_selection)
        self.layers.visibilityToggled.connect(lambda i, v: self._set_flag(i, "visible", v))
        self.layers.lockToggled.connect(lambda i, v: self._set_flag(i, "locked", v))
        self.layers.renamed.connect(self._rename)
        self.layers.reorderRequested.connect(self.reorder)
        self.layers.groupRequested.connect(self.group_selected)
        self.layers.ungroupRequested.connect(self.ungroup_selected)
        self.layers.setMinimumWidth(220)
        if self.preview:  # порядок і групи в картці товару не змінюються
            for button in self.layers.buttons.values():
                button.hide()

        self.view = CanvasView()
        self.view.zoomChanged.connect(lambda z: self.zoom_label.setText(f"{round(z * 100)} %"))
        self.properties = PropertiesPanel(self.workspace, preview=self.preview)
        self.properties.changed.connect(self._properties_changed)
        self.properties.actionRequested.connect(self._panel_action)
        self.properties.cellsSelected.connect(self._cells_selected)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.properties)
        scroll.setMinimumWidth(370)

        splitter = QSplitter()
        splitter.addWidget(self.layers)
        splitter.addWidget(self.view)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 800, 380])

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addLayout(tools)
        layout.addWidget(splitter, 1)

    def _build_actions(self) -> None:
        def action(text, shortcut, handler):
            a = QAction(text, self)
            a.setShortcuts(shortcut if isinstance(shortcut, list) else [QKeySequence(shortcut)])
            a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            a.triggered.connect(handler)
            self.addAction(a)
            return a

        action("Зберегти", QKeySequence.StandardKey.Save, self.save_now)
        action("Скасувати", QKeySequence.StandardKey.Undo, self.undo)
        action("Повторити", [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")], self.redo)
        action("Копіювати", QKeySequence.StandardKey.Copy, self.copy_selected)
        action("Вирізати", QKeySequence.StandardKey.Cut, self.cut_selected)
        action("Вставити", QKeySequence.StandardKey.Paste, self.paste)
        action("Дублювати", "Ctrl+D", self.duplicate_selected)
        action("Виділити все", QKeySequence.StandardKey.SelectAll, self.select_all)
        action("Згрупувати", "Ctrl+G", self.group_selected)
        action("Розгрупувати", "Ctrl+Shift+G", self.ungroup_selected)
        action("Вище", "Ctrl+]", lambda: self.reorder("up"))
        action("Нижче", "Ctrl+[", lambda: self.reorder("down"))
        action("Нагору", "Ctrl+Shift+]", lambda: self.reorder("front"))
        action("Донизу", "Ctrl+Shift+[", lambda: self.reorder("back"))
        action("Сітка", "Ctrl+'", lambda: self.grid_box.toggle())

        # клавіші, які потрібні й полям введення, діють лише на полотні та в шарах
        for widget in (self.view, self.layers.tree):
            self._local_shortcut(widget, QKeySequence.StandardKey.Delete, self.delete_selected)
        self._local_shortcut(self.view, Qt.Key.Key_Escape, self.select_canvas)
        for key, (dx, dy) in {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0),
                              Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}.items():
            self._local_shortcut(self.view, key, lambda dx=dx, dy=dy: self.nudge(dx, dy))
            self._local_shortcut(self.view, Qt.KeyboardModifier.ShiftModifier | key,
                                 lambda dx=dx, dy=dy: self.nudge(dx * 10, dy * 10))

    @staticmethod
    def _local_shortcut(widget, key, handler) -> None:
        shortcut = QShortcut(QKeySequence(key), widget, handler)
        shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)

    # --- Відкриття / стан ---------------------------------------------------

    def open_template(self, category_id: str, template_id: str) -> None:
        self.category_id = category_id
        template = self.workspace.load_template(category_id, template_id)
        self.history.clear()
        self.entered_group = None
        self._set_template(template, set())
        self.properties.category_id = category_id
        self.title.setText(template.name)
        self.dirty = False
        self._set_status("Збережено")
        QTimer.singleShot(0, self.view.fit_canvas)

    def _set_template(self, template: Template, select: set[str]) -> None:
        """Показати шаблон на полотні (при відкритті та при Undo/Redo)."""
        ops.update_all_group_bounds(template)
        self.template = template
        self._snapshot = template_to_dict(template)
        self.ctx = RenderContext(self.workspace, self.category_id, data_images=self.data_images,
                                 placeholders=not self.preview)
        old = self.scene
        self.scene = EditorScene(template, self.ctx, parent=self)
        self._apply_grid_settings()
        for element in ops.leaves(template.elements):
            self._attach(self.scene.add_element_item(element))
        self._sync_inherited()
        self.scene.restack()
        self.scene.selectionChanged.connect(self._scene_selection_changed)
        transform = self.view.transform()
        center = self.view.mapToScene(self.view.viewport().rect().center())
        self.view.setScene(self.scene)
        self.view.setTransform(transform)
        self.view.centerOn(center)
        if old is not None:
            old.selectionChanged.disconnect(self._scene_selection_changed)
            old.deleteLater()
        self.properties.template = template
        if self.entered_group and ops.find(template, self.entered_group) is None:
            self.entered_group = None
        self.layers.rebuild(template, set())
        self.select_ids(select)
        self._update_undo_buttons()

    def _attach(self, item: ElementItem) -> None:
        item.moved.connect(self._item_moved)
        item.committed.connect(lambda _id, label: self.commit(label))
        item.doubleClicked.connect(self._item_double_clicked)
        item.cellClicked.connect(self._cell_clicked)

    def _sync_inherited(self) -> None:
        """Передати блокам приховування, замок і прозорість їхніх груп."""
        def walk(elements, hidden, locked, opacity):
            for e in elements:
                if isinstance(e, GroupElement):
                    walk(e.children, hidden or not e.visible, locked or e.locked, opacity * e.opacity)
                    continue
                item = self.scene.items_by_id.get(e.id)
                if item is not None:
                    item.parent_hidden, item.parent_locked, item.parent_opacity = hidden, locked, opacity
                    item.sync_from_model()

        walk(self.template.elements, False, False, 1.0)

    # --- Історія й збереження -----------------------------------------------

    def commit(self, label: str, merge_key: str | None = None, *, structure: bool = False) -> None:
        """Зафіксувати дію: історія + автозбереження. structure — змінився склад/порядок блоків."""
        ops.update_all_group_bounds(self.template)
        after = template_to_dict(self.template)
        self.history.push(self._snapshot, after, label, merge_key)
        self._snapshot = after
        if structure:
            self.scene.restack()
            self._sync_inherited()
            self.layers.rebuild(self.template, set(self.selection_ids()))
        self._update_undo_buttons()
        self.mark_dirty()

    def undo(self) -> None:
        state = self.history.undo()
        if state is not None:
            self._restore(state)

    def redo(self) -> None:
        state = self.history.redo()
        if state is not None:
            self._restore(state)

    def _restore(self, state: dict) -> None:
        selected = set(self.selection_ids())
        self._set_template(template_from_dict(state), selected)
        self.mark_dirty()

    def _update_undo_buttons(self) -> None:
        self.undo_button.setEnabled(self.history.can_undo())
        self.redo_button.setEnabled(self.history.can_redo())
        self.undo_button.setToolTip(f"Скасувати: {self.history.undo_label()} (Ctrl+Z)"
                                    if self.history.can_undo() else "Нічого скасовувати")
        self.redo_button.setToolTip(f"Повторити: {self.history.redo_label()} (Ctrl+Y)"
                                    if self.history.can_redo() else "Нічого повторювати")

    def mark_dirty(self) -> None:
        self.dirty = True
        if self.preview:
            self._set_status("Є незбережені правки")
            self.changed.emit()
            return
        self._set_status("Є зміни…")
        self._save_timer.start()

    def open_card(self, category_id: str, card: Template, data_images, title: str) -> None:
        """Режим перегляду: показати готову картку товару для правок."""
        self.category_id = category_id
        self.data_images = data_images
        self.history.clear()
        self.entered_group = None
        self._set_template(card, set())
        self.properties.category_id = category_id
        self.title.setText(title)
        self.dirty = False
        self._set_status("")

    def save_now(self) -> bool:
        self._save_timer.stop()
        if self.preview:
            return True  # картку зберігає екран перегляду
        if self.template is None or not self.dirty:
            return True
        try:
            self.workspace.save_template(self.category_id, self.template)
        except (StorageError, OSError) as e:
            self._set_status("Не збережено!")
            dialogs.error(self, f"Не вдалося зберегти шаблон: {e}")
            return False
        self.dirty = False
        self._set_status("Збережено")
        return True

    def leave(self) -> None:
        if self.save_now():
            self.back.emit()

    def _open_preview(self) -> None:
        if self.template is not None and self.save_now():
            self.open_preview.emit(self.category_id, self.template.id)

    def _open_data(self) -> None:
        if self.template is not None and self.save_now():
            self.open_data.emit(self.category_id, self.template.id)

    def _set_status(self, text: str) -> None:
        self.status.setText(text)

    # --- Виділення ----------------------------------------------------------

    def selected_items(self) -> list[ElementItem]:
        if self.scene is None:
            return []
        return [i for i in self.scene.selectedItems() if isinstance(i, ElementItem)]

    def _unit_of(self, leaf_id: str) -> Element | None:
        """Що насправді вибирає клік по блоку: сам блок, групу верхнього рівня
        або (усередині групи, куди «зайшли») її безпосередню дитину."""
        container = self.template.elements
        if self.entered_group:
            group = ops.find(self.template, self.entered_group)
            if isinstance(group, GroupElement) and any(
                    e.id == leaf_id for e in ops.leaves(group.children)):
                container = group.children
        for e in container:
            if e.id == leaf_id or (isinstance(e, GroupElement)
                                   and any(c.id == leaf_id for c in ops.leaves(e.children))):
                return e
        return ops.find(self.template, leaf_id)

    def selection_units(self) -> list[Element]:
        seen: dict[str, Element] = {}
        for item in self.selected_items():
            unit = self._unit_of(item.element.id)
            if unit is not None:  # None — блок щойно видалено з шаблону
                seen.setdefault(unit.id, unit)
        return ops.topmost_units(self.template, seen)

    def selection_ids(self) -> list[str]:
        return [u.id for u in self.selection_units()]

    def selected_element(self) -> Element | None:
        units = self.selection_units()
        return units[0] if len(units) == 1 else None

    def select_ids(self, ids) -> None:
        """Виділити блоки/групи за id (групу — усіма її блоками)."""
        if self.scene is None:
            return
        wanted = set()
        for element_id in ids:
            element = ops.find(self.template, element_id)
            if element is not None:
                wanted.update(e.id for e in ops.leaves([element]))
        self._selecting = True
        self.scene.clearSelection()
        for element_id in wanted:
            item = self.scene.items_by_id.get(element_id)
            if item is not None:
                item.setSelected(True)
        self._selecting = False
        self._scene_selection_changed()

    def select_element(self, element_id: str) -> None:
        self.select_ids([element_id])
        self.view.setFocus()

    def select_canvas(self) -> None:
        self.entered_group = None
        if self.scene is not None:
            self.scene.clearSelection()

    def select_all(self) -> None:
        self.entered_group = None
        self.select_ids([e.id for e in self.template.elements if e.visible])

    def _scene_selection_changed(self) -> None:
        if self._selecting or self.scene is None:
            return
        items = self.selected_items()
        # вийти з групи, якщо вибрано щось поза нею
        if self.entered_group:
            group = ops.find(self.template, self.entered_group)
            inside = {e.id for e in ops.leaves(group.children)} if group else set()
            if not items or any(i.element.id not in inside for i in items):
                self.entered_group = None
        units = self.selection_units()
        wanted = {e.id for u in units for e in ops.leaves([u])}
        if wanted != {i.element.id for i in items}:
            self._selecting = True
            for element_id in wanted:
                self.scene.items_by_id[element_id].setSelected(True)
            self._selecting = False
        self.history.seal()

        self.scene.group_outlines = [self._unit_rect(u) for u in units if isinstance(u, GroupElement)]
        self.scene.update()
        for item in self.scene.items_by_id.values():
            item.prepareGeometryChange()  # маркери з'являються лише при одному блоці
        self.layers.select_ids({u.id for u in units})
        if len(units) == 1:
            self.properties.set_target(units[0])
        elif not units:
            self.properties.set_target(self.template)
        else:
            self.properties.set_target(units)
        self._cells_selected(self.properties.table_cells)

    def _layers_selection(self, ids: list[str]) -> None:
        if ids:
            parent = ops.parent_group(self.template, ids[0])
            self.entered_group = parent.id if parent is not None else None
        else:
            self.entered_group = None
        self.select_ids(ids)

    def _item_double_clicked(self, leaf_id: str) -> None:
        group = ops.parent_group(self.template, leaf_id)
        if group is not None:
            self.entered_group = group.id
            self.select_ids([leaf_id])
        element = ops.find(self.template, leaf_id)
        if isinstance(element, TextElement):
            editor = self.properties.findChild(QPlainTextEdit, "text")
            if editor is not None:
                editor.setFocus()
                editor.selectAll()

    # --- Клітинки таблиці ------------------------------------------------------

    def _cell_clicked(self, table_id: str, row: int, col: int, add: bool) -> None:
        if self.properties.target is None or getattr(self.properties.target, "id", None) != table_id:
            return  # клік виділив групу, а не саму таблицю
        cells = set(self.properties.table_cells) if add else set()
        cells.add((row, col))
        self.properties.select_cells(cells)

    def _cells_selected(self, cells: set) -> None:
        for item in self.scene.items_by_id.values():
            if isinstance(item.element, TableElement):
                is_current = item.element is self.properties.target
                item.selected_cells = set(cells) if is_current else set()
                item.update()

    def _unit_rect(self, unit: Element) -> QRectF:
        rect = QRectF()
        for leaf in ops.leaves([unit]):
            item = self.scene.items_by_id.get(leaf.id)
            if item is not None:
                rect = rect.united(item.scene_rect())
        return rect

    # --- Зміни з панелей та полотна -------------------------------------------

    def _item_moved(self, element_id: str) -> None:
        target = self.properties.target
        if isinstance(target, Element):
            self.properties.refresh()
        if self.scene.group_outlines:
            self.scene.group_outlines = [self._unit_rect(u) for u in self.selection_units()
                                         if isinstance(u, GroupElement)]
            self.scene.update()

    def _properties_changed(self, target, key: str) -> None:
        if isinstance(target, Template):
            self.scene.update_scene_rect()
            self.scene.update()
            self.commit("Полотно", key)
            return
        if isinstance(target, GroupElement):
            self._sync_inherited()
        elif isinstance(target, Element):
            item = self.scene.items_by_id.get(target.id)
            if item is not None:
                item.sync_from_model()
        structure = key.endswith((":name", ":locked"))
        self.commit("Властивості", key, structure=structure)

    def _panel_action(self, action: str) -> None:
        if action == "group":
            self.group_selected()
        elif action == "ungroup":
            self.ungroup_selected()
        elif action.startswith("align_"):
            self.align(action[len("align_"):])
        elif action.startswith("distribute_"):
            self.distribute(action[-1])

    def _set_flag(self, element_id: str, attr: str, value: bool) -> None:
        element = ops.find(self.template, element_id)
        if element is None or getattr(element, attr) == value:
            return
        setattr(element, attr, value)
        self._sync_inherited()
        self.commit("Видимість" if attr == "visible" else "Замок", structure=True)
        self.properties.refresh()

    def _rename(self, element_id: str, name: str) -> None:
        element = ops.find(self.template, element_id)
        if element is not None and name and element.name != name:
            element.name = name
            self.commit("Перейменування", structure=True)
            self.properties.refresh()

    def nudge(self, dx: float, dy: float) -> None:
        units = [u for u in self.selection_units() if not self._is_locked(u)]
        for unit in units:
            ops.move_by(unit, dx, dy)
            for leaf in ops.leaves([unit]):
                self.scene.items_by_id[leaf.id].sync_from_model()
        if units:
            self.properties.refresh()
            self._item_moved("")
            self.commit("Зсув", "nudge:" + ",".join(u.id for u in units))

    def _is_locked(self, element: Element) -> bool:
        if element.locked:
            return True
        group = ops.parent_group(self.template, element.id)
        return group is not None and self._is_locked(group)

    # --- Додавання, видалення, копіювання -------------------------------------

    def _next_name(self, key: str) -> str:
        prefix = NAME_PREFIX[key]
        taken = {e.name for e in ops.iter_elements(self.template.elements)}
        n = 1
        while f"{prefix} {n}" in taken:
            n += 1
        return f"{prefix} {n}"

    def make_block(self, key: str) -> Element | None:
        t = self.template
        if key == "text":
            element = TextElement(width=t.width * 0.5, height=t.height * 0.1, text="Текст",
                                  style=TextStyle(font_size=round(t.height * 0.05)))
        elif key == "rect":
            element = ShapeElement(width=t.width * 0.3, height=t.height * 0.2, corner_radius=16,
                                   fill=Paint(color="#1E5BFF"))
        elif key == "ellipse":
            side = min(t.width, t.height) * 0.2
            element = ShapeElement(shape="ellipse", width=side, height=side, fill=Paint(color="#1E5BFF"))
        elif key == "line":
            element = ShapeElement(shape="line", width=t.width * 0.4, height=20,
                                   fill=Paint(kind="none"), stroke=Stroke(color="#111111", width=4))
        elif key == "icon":
            ref = pick_asset(self, self.workspace, "icons")
            if ref is None:
                return None
            side = min(t.width, t.height) * 0.12
            element = IconElement(width=side, height=side, asset=ref)
        elif key == "photo":
            side = min(t.width, t.height) * 0.5
            element = PhotoElement(width=side, height=side)
        elif key == "table":
            element = make_table(t.width * 0.8, t.height * 0.35, round(t.height * 0.028))
        else:
            raise ValueError(key)
        element.name = self._next_name(key)
        element.x = (t.width - element.width) / 2
        element.y = (t.height - element.height) / 2
        return element

    def add_block(self, key: str) -> Element | None:
        element = self.make_block(key)
        if element is not None:
            self.add_elements([element], "Новий блок")
        return element

    def add_elements(self, elements: list[Element], label: str,
                     container: list[Element] | None = None, index: int | None = None) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        container = self.template.elements if container is None else container
        if index is None:
            container.extend(elements)
        else:
            container[index:index] = elements
        for element in elements:
            for leaf in ops.leaves([element]):
                self._attach(self.scene.add_element_item(leaf))
        self.commit(label, structure=True)
        self.entered_group = None
        self.select_ids([e.id for e in elements])
        self.view.setFocus()

    def delete_selected(self) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        units = self.selection_units()
        if not units:
            return
        leaf_ids = [leaf.id for u in units for leaf in ops.leaves([u])]
        ops.delete(self.template, [u.id for u in units])
        self._selecting = True
        for element_id in leaf_ids:
            self.scene.remove_element_item(element_id)
        self._selecting = False
        self.commit("Видалення", structure=True)
        self._scene_selection_changed()

    def copy_selected(self) -> bool:
        units = self.selection_units()
        if not units:
            return False
        CLIPBOARD[:] = [to_dict(u) for u in units]
        self._paste_count = 0
        return True

    def cut_selected(self) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        if self.copy_selected():
            self.delete_selected()

    def paste(self) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        if not CLIPBOARD:
            return
        self._paste_count += 1
        offset = PASTE_OFFSET * self._paste_count
        pasted = []
        for data in CLIPBOARD:
            element = ops.clone(from_dict(Element, data))
            ops.move_by(element, offset, offset)
            pasted.append(element)
        self.add_elements(pasted, "Вставлення")

    def duplicate_selected(self) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        units = self.selection_units()
        if not units:
            return
        copies = []
        for unit in units:
            copy = ops.clone(unit)
            ops.move_by(copy, PASTE_OFFSET, PASTE_OFFSET)
            siblings = ops.parent_list(self.template, unit.id)
            siblings.insert(siblings.index(unit) + 1, copy)
            for leaf in ops.leaves([copy]):
                self._attach(self.scene.add_element_item(leaf))
            copies.append(copy)
        self.commit("Дублювання", structure=True)
        self.select_ids([c.id for c in copies])

    # --- Групи й порядок --------------------------------------------------------

    def group_selected(self) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        units = self.selection_units()
        if len(units) < 2:
            return
        try:
            group = ops.group(self.template, [u.id for u in units], self._next_name("group"))
        except ops.OpError as e:
            dialogs.error(self, str(e))
            return
        self.entered_group = None
        self.commit("Групування", structure=True)
        self.select_ids([group.id])

    def ungroup_selected(self) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        groups = [u for u in self.selection_units() if isinstance(u, GroupElement)]
        if not groups:
            return
        children = []
        for g in groups:
            children += ops.ungroup(self.template, g.id)
        self.entered_group = None
        self.commit("Розгрупування", structure=True)
        self.select_ids(children)

    def reorder(self, mode: str) -> None:
        if self.preview:  # у картці товару склад і порядок блоків не змінюються
            return
        ids = self.selection_ids()
        if not ids:
            return
        ops.reorder(self.template, ids, mode)
        self.commit("Порядок шарів", structure=True)
        self.select_ids(ids)

    # --- Вирівнювання -------------------------------------------------------------

    def align(self, mode: str) -> None:
        units = [u for u in self.selection_units() if not self._is_locked(u)]
        if not units:
            return
        rects = {u.id: self._unit_rect(u) for u in units}
        if len(self.selection_units()) == 1:
            ref = self.scene.canvas_rect()
        else:
            ref = QRectF()
            for r in rects.values():
                ref = ref.united(r)
        for unit in units:
            r = rects[unit.id]
            dx = dy = 0.0
            if mode == "left":
                dx = ref.left() - r.left()
            elif mode == "hcenter":
                dx = ref.center().x() - r.center().x()
            elif mode == "right":
                dx = ref.right() - r.right()
            elif mode == "top":
                dy = ref.top() - r.top()
            elif mode == "vcenter":
                dy = ref.center().y() - r.center().y()
            elif mode == "bottom":
                dy = ref.bottom() - r.bottom()
            self._move_unit(unit, dx, dy)
        self.commit("Вирівнювання")

    def distribute(self, axis: str) -> None:
        """Рівні проміжки між блоками: axis 'h' — по ширині, 'v' — по висоті."""
        units = [u for u in self.selection_units() if not self._is_locked(u)]
        if len(units) < 3:
            return
        rects = {u.id: self._unit_rect(u) for u in units}
        if axis == "h":
            units.sort(key=lambda u: rects[u.id].center().x())
            first, last = rects[units[0].id], rects[units[-1].id]
            gap = (last.right() - first.left() - sum(rects[u.id].width() for u in units)) / (len(units) - 1)
            pos = first.left()
            for unit in units:
                self._move_unit(unit, pos - rects[unit.id].left(), 0)
                pos += rects[unit.id].width() + gap
        else:
            units.sort(key=lambda u: rects[u.id].center().y())
            first, last = rects[units[0].id], rects[units[-1].id]
            gap = (last.bottom() - first.top() - sum(rects[u.id].height() for u in units)) / (len(units) - 1)
            pos = first.top()
            for unit in units:
                self._move_unit(unit, 0, pos - rects[unit.id].top())
                pos += rects[unit.id].height() + gap
        self.commit("Розподіл")

    def _move_unit(self, unit: Element, dx: float, dy: float) -> None:
        if not dx and not dy:
            return
        ops.move_by(unit, dx, dy)
        for leaf in ops.leaves([unit]):
            self.scene.items_by_id[leaf.id].sync_from_model()
        self._item_moved(unit.id)

    # --- Сітка, прилипання, масштаб ---------------------------------------------

    def _apply_grid_settings(self) -> None:
        if self.scene is None:
            return
        self.scene.snap_enabled = self.snap_box.isChecked()
        self.scene.grid_enabled = self.grid_box.isChecked()
        self.scene.grid_size = float(self.grid_size.value())
        self.scene.update()

    def _grid_settings_changed(self, *_args) -> None:
        self._apply_grid_settings()
        self.workspace.save_editor_settings(snap=self.snap_box.isChecked(), grid=self.grid_box.isChecked(),
                                            grid_size=self.grid_size.value())

    def _zoom_selected(self, index: int) -> None:
        value = self.zoom_box.itemData(index)
        if value:
            self.view.set_zoom(value)
            self.view.centerOn(self.scene.canvas_rect().center())
        else:
            self.view.fit_canvas()
