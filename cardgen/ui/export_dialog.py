"""Діалог експорту карток у JPEG: які шаблони, куди, прогрес і звіт."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..export import PRESETS, ExportReport, export_cards
from ..products import Products
from ..storage import Workspace
from . import dialogs


class ExportDialog(QDialog):
    def __init__(self, workspace: Workspace, category_id: str, selected: list[str] | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.workspace = workspace
        self.category_id = category_id
        self.report: ExportReport | None = None
        self.setWindowTitle("Експорт карток у JPEG")
        self.resize(620, 520)

        self.templates = QListWidget()
        self.templates.setObjectName("exportTemplates")
        self.counts: dict[str, int] = {}
        for template in workspace.list_templates(category_id):
            products = Products(workspace, category_id, template.id)
            errors = len({i.row for i in products.issues if i.level == "error" and i.row >= 0})
            self.counts[template.id] = len(products)
            text = f"{template.name}   ·   №{template.export.number}   ·   карток: {len(products)}"
            if errors:
                text += f"   ·   з помилками: {errors}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, template.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = (template.id in selected) if selected else len(products) > 0
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            if not len(products):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                item.setToolTip("Немає даних товарів")
            self.templates.addItem(item)
        self.templates.itemChanged.connect(lambda _i: self._update_total())

        last = workspace.editor_settings().get("export_folder", "")
        self.folder = QLineEdit(last)
        self.folder.setObjectName("exportFolder")
        self.folder.setPlaceholderText("Папка, куди зберегти картки")
        browse = QPushButton("Вибрати…")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)

        self.skip_errors = QCheckBox("Не експортувати картки з помилками в даних")
        self.skip_errors.setObjectName("skipErrors")
        preset = PRESETS["prom_rozetka"]
        info = QLabel(f"Профіль «{preset.title}»: JPEG, RGB, найбільша сторона до {preset.max_side} px "
                      f"(більші картки зменшуються), файл до {preset.max_bytes // 1024 // 1024} МБ. "
                      "Файли з такими самими іменами в папці буде перезаписано.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #6B7280;")
        self.total = QLabel()
        self.total.setObjectName("exportTotal")

        export = QPushButton("Експортувати")
        export.setObjectName("btn_export")
        export.setDefault(True)
        export.clicked.connect(self.run_export)
        cancel = QPushButton("Закрити")
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.total)
        buttons.addStretch()
        buttons.addWidget(export)
        buttons.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Шаблони (кожен шаблон — окрема картинка товару):"))
        layout.addWidget(self.templates, 1)
        layout.addWidget(QLabel("Папка:"))
        layout.addLayout(folder_row)
        layout.addWidget(self.skip_errors)
        layout.addWidget(info)
        layout.addLayout(buttons)
        self._update_total()

    def chosen(self) -> list[str]:
        result = []
        for i in range(self.templates.count()):
            item = self.templates.item(i)
            if item.checkState() == Qt.CheckState.Checked and item.flags() & Qt.ItemFlag.ItemIsEnabled:
                result.append(item.data(Qt.ItemDataRole.UserRole))
        return result

    def _update_total(self) -> None:
        self.total.setText(f"Усього карток: {sum(self.counts[t] for t in self.chosen())}")

    def _browse(self) -> None:
        folder = dialogs.open_dir(self, "Куди зберегти картки", self.folder.text())
        if folder is not None:
            self.folder.setText(str(folder))

    def run_export(self) -> ExportReport | None:
        templates = self.chosen()
        if not templates:
            dialogs.error(self, "Виберіть хоча б один шаблон з даними")
            return None
        if not self.folder.text().strip():
            self._browse()
            if not self.folder.text().strip():
                return None
        folder = Path(self.folder.text().strip())
        self.workspace.save_editor_settings(export_folder=str(folder))
        total = sum(self.counts[t] for t in templates)

        progress = QProgressDialog("Експорт карток…", "Зупинити", 0, total, self)
        progress.setWindowTitle("Експорт")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(300)

        def step(done: int, name: str) -> bool:
            progress.setValue(done)
            if name:
                progress.setLabelText(f"{done + 1} з {total}: {name}")
            QApplication.processEvents()
            return not progress.wasCanceled()

        try:
            report = export_cards(self.workspace, self.category_id, templates, folder,
                                  skip_errors=self.skip_errors.isChecked(), progress=step)
        except OSError as e:
            progress.close()
            dialogs.error(self, f"Не вдалося записати файли: {e}")
            return None
        progress.close()
        self.report = report
        self._show_report(report, folder)
        return report

    def _show_report(self, report: ExportReport, folder: Path) -> None:
        lines = [("Експорт зупинено. " if report.cancelled else "") + f"Збережено карток: {len(report.files)}"]
        if report.skipped:
            lines.append(f"\nПропущено (помилки в даних): {len(report.skipped)}")
            lines += [f"• {s}" for s in report.skipped[:10]]
        if report.warnings:
            lines.append(f"\nЗауваження: {len(report.warnings)}")
            lines += [f"• {w}" for w in report.warnings[:10]]
            if len(report.warnings) > 10:
                lines.append(f"… і ще {len(report.warnings) - 10}")
        lines.append(f"\nПапка: {folder}")
        dialogs.info(self, "Експорт", "\n".join(lines))
        if report.files and dialogs.confirm(self, "Експорт", "Відкрити папку з картками?"):
            os.startfile(folder)


def ask_export(parent: QWidget, workspace: Workspace, category_id: str,
               selected: list[str] | None = None) -> None:
    ExportDialog(workspace, category_id, selected, parent).exec()
