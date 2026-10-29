"""Діалог створення шаблону / зміни назви, розміру полотна й налаштувань експорту."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from ..model.template import DEFAULT_FILENAME_MASK

PRESETS = [
    ("1000 × 1000", 1000, 1000),
    ("1200 × 1200", 1200, 1200),
    ("1280 × 1280", 1280, 1280),
    ("1000 × 1333 (3:4)", 1000, 1333),
]
CUSTOM = "Свій розмір"


@dataclass
class TemplateValues:
    name: str
    width: int
    height: int
    number: int = 1
    filename_mask: str = DEFAULT_FILENAME_MASK
    jpeg_quality: int = 92


class TemplateDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, title: str = "Новий шаблон",
                 values: TemplateValues | None = None, show_export: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        values = values or TemplateValues("", 1000, 1000)

        self.name_edit = QLineEdit(values.name)
        self.name_edit.setPlaceholderText("Наприклад: Обкладинка")
        self.preset = QComboBox()
        for label, _, _ in PRESETS:
            self.preset.addItem(label)
        self.preset.addItem(CUSTOM)
        self.width_spin = QSpinBox()
        self.height_spin = QSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(100, 6000)
            spin.setSuffix(" px")
        self.width_spin.setValue(values.width)
        self.height_spin.setValue(values.height)
        self._sync_preset()

        self.preset.currentIndexChanged.connect(self._apply_preset)
        self.width_spin.valueChanged.connect(self._sync_preset)
        self.height_spin.valueChanged.connect(self._sync_preset)

        self.number_spin = QSpinBox()
        self.number_spin.setObjectName("number")
        self.number_spin.setRange(1, 99)
        self.number_spin.setValue(values.number)
        self.mask_edit = QLineEdit(values.filename_mask)
        self.mask_edit.setObjectName("mask")
        self.quality_spin = QSpinBox()
        self.quality_spin.setObjectName("quality")
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(values.jpeg_quality)
        self.example = QLabel()
        self.example.setStyleSheet("color: #6B7280;")
        self.mask_edit.textChanged.connect(self._update_example)
        self.number_spin.valueChanged.connect(self._update_example)
        self._update_example()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("Назва:", self.name_edit)
        form.addRow("Розмір полотна:", self.preset)
        form.addRow("Ширина:", self.width_spin)
        form.addRow("Висота:", self.height_spin)
        if show_export:
            header = QLabel("Експорт JPEG")
            header.setStyleSheet("font-weight: 600; padding-top: 10px;")
            form.addRow(header)
            form.addRow("Номер картинки:", self.number_spin)
            form.addRow("Ім'я файлу:", self.mask_edit)
            form.addRow("", self.example)
            hint = QLabel("{Артикул} або будь-який стовпець даних, {№} — номер картинки, "
                          "{шаблон} — назва шаблону")
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #6B7280;")
            form.addRow("", hint)
            form.addRow("Якість JPEG:", self.quality_spin)
        form.addRow(buttons)

    def values(self) -> TemplateValues:
        return TemplateValues(self.name_edit.text(), self.width_spin.value(), self.height_spin.value(),
                              self.number_spin.value(), self.mask_edit.text().strip() or DEFAULT_FILENAME_MASK,
                              self.quality_spin.value())

    def _update_example(self) -> None:
        sample = (self.mask_edit.text() or DEFAULT_FILENAME_MASK)
        sample = sample.replace("{Артикул}", "AWG-18").replace("{№}", str(self.number_spin.value()))
        sample = sample.replace("{шаблон}", self.name_edit.text() or "Обкладинка")
        self.example.setText(f"Наприклад: {sample}.jpg")

    def _apply_preset(self, index: int) -> None:
        if index < len(PRESETS):
            _, w, h = PRESETS[index]
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)

    def _sync_preset(self) -> None:
        size = (self.width_spin.value(), self.height_spin.value())
        index = next((i for i, (_, w, h) in enumerate(PRESETS) if (w, h) == size), len(PRESETS))
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(index)
        self.preset.blockSignals(False)


def ask_template(parent: QWidget, **kwargs) -> TemplateValues | None:
    dialog = TemplateDialog(parent, **kwargs)
    return dialog.values() if dialog.exec() == QDialog.DialogCode.Accepted else None
