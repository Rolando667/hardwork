"""Вкладка «Результати»: зведена таблиця, підсумки, експорт і збереження прогону."""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import config, exporter, storage
from core.aggregate import Aggregation, aggregate, cell_display
from core.models import Dialog, ModelConfig, RunCell
from core.serialize import build_run_payload, parse_run_payload

_GREEN = QColor("#2f6b3d")
_RED = QColor("#7a2f2f")
_WHITE = QColor("#ffffff")


def _fmt_cost(value) -> str:
    if value is None:
        return "—"
    return f"${value:.4f}"


def _fmt_tokens(value) -> str:
    return "—" if value is None else str(value)


class ResultsTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._models: List[ModelConfig] = []
        self._dialogs: List[Dialog] = []
        self._levels: List[str] = []
        self._results: List[RunCell] = []
        self._agg: Aggregation | None = None
        self._prompt_name: str = ""
        self._prompt_text: str = ""

        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        self.summary_table = QTableWidget(0, 0)
        self.summary_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.summary_table.verticalHeader().setVisible(False)
        self.summary_table.setMaximumHeight(190)
        self.summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

        self.total_label = QLabel("Загальна вартість прогону: —")
        self.total_label.setStyleSheet("font-weight: bold;")
        self.status_label = QLabel("")
        self.status_label.setObjectName("hint")

        self.csv_btn = QPushButton("Експорт CSV")
        self.csv_btn.setObjectName("secondary")
        self.xlsx_btn = QPushButton("Експорт XLSX")
        self.xlsx_btn.setObjectName("secondary")
        self.save_btn = QPushButton("Зберегти прогін")
        self.open_btn = QPushButton("Відкрити збережений прогін")
        self.open_btn.setObjectName("secondary")
        self.csv_btn.clicked.connect(self._export_csv)
        self.xlsx_btn.clicked.connect(self._export_xlsx)
        self.save_btn.clicked.connect(lambda: self._save_run(auto=False))
        self.open_btn.clicked.connect(self._open_run)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.csv_btn)
        btn_row.addWidget(self.xlsx_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.open_btn)
        btn_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Зведена таблиця (рядки — діалоги, колонки — модель @ рівень):"))
        layout.addWidget(self.table, 3)
        layout.addWidget(QLabel("Підсумки по колонках:"))
        layout.addWidget(self.summary_table, 1)
        layout.addWidget(self.total_label)
        layout.addLayout(btn_row)
        layout.addWidget(self.status_label)

    # ---------------- Завантаження результатів ----------------

    def load(
        self,
        results: List[RunCell],
        context: Dict[str, Any],
        *,
        auto_save: bool = True,
    ) -> None:
        self._results = results
        self._models = context.get("models", [])
        self._dialogs = context.get("dialogs", [])
        self._levels = context.get("levels", [])
        self._prompt_name = context.get("prompt_name", "")
        self._prompt_text = context.get("prompt_text", "")
        self._repeats = context.get("repeats", 1)
        self._parallel = context.get("parallel", 2)

        self._agg = aggregate(self._results, self._models, self._levels, self._dialogs)
        self._build_table()
        self._build_summary()
        self.total_label.setText(
            f"Загальна вартість прогону: {_fmt_cost(self._agg.total_cost)}"
        )
        if auto_save:
            self._save_run(auto=True)

    def _build_table(self) -> None:
        assert self._agg is not None
        agg = self._agg
        self.table.setSortingEnabled(False)
        columns = agg.columns
        headers = ["Діалог", "Еталон"] + [c.label for c in columns]
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(self._dialogs))

        for r, dialog in enumerate(self._dialogs):
            name_item = QTableWidgetItem(dialog.name)
            name_item.setToolTip(dialog.text)
            self.table.setItem(r, 0, name_item)
            self.table.setItem(r, 1, QTableWidgetItem(dialog.etalon))
            for c, col in enumerate(columns, start=2):
                cell = agg.cells.get((dialog.id, col.model_id, col.level))
                item = QTableWidgetItem()
                if cell is None:
                    item.setText("—")
                    self.table.setItem(r, c, item)
                    continue
                display = cell_display(cell)
                metrics = (
                    f"{_fmt_tokens(cell.tokens_in)}/{_fmt_tokens(cell.tokens_out)} · "
                    f"{_fmt_cost(cell.cost)} · {cell.avg_seconds:.1f}с"
                )
                item.setText(f"{display}\n{metrics}")
                tooltip_lines = [
                    f"Трансляція: {cell.translation}",
                ]
                if cell.error:
                    tooltip_lines.append(f"Помилка: {cell.error}")
                if cell.comment:
                    tooltip_lines.append(f"Коментар: {cell.comment}")
                tooltip_lines.append("")
                tooltip_lines.append("Сира відповідь:")
                tooltip_lines.append(cell.raw or "—")
                item.setToolTip("\n".join(tooltip_lines))
                if cell.color == "green":
                    item.setBackground(QBrush(_GREEN))
                    item.setForeground(QBrush(_WHITE))
                elif cell.color == "red":
                    item.setBackground(QBrush(_RED))
                    item.setForeground(QBrush(_WHITE))
                self.table.setItem(r, c, item)

        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()
        self.table.setSortingEnabled(True)

    def _build_summary(self) -> None:
        assert self._agg is not None
        agg = self._agg
        metrics = [
            "Збігів з еталоном",
            "Хибних алертів",
            "Пропусків",
            "Сумарна вартість $",
            "Середній час, с",
        ]
        columns = agg.columns
        self.summary_table.setColumnCount(1 + len(columns))
        self.summary_table.setHorizontalHeaderLabels(["Метрика"] + [c.label for c in columns])
        self.summary_table.setRowCount(len(metrics))
        for r, metric in enumerate(metrics):
            self.summary_table.setItem(r, 0, QTableWidgetItem(metric))
        for c, col in enumerate(columns, start=1):
            s = agg.col_summary.get((col.model_id, col.level))
            if s is None:
                continue
            values = [
                str(s.matches),
                str(s.false_alerts),
                str(s.misses),
                f"{s.cost:.4f}",
                f"{s.avg_time:.1f}",
            ]
            for r, value in enumerate(values):
                self.summary_table.setItem(r, c, QTableWidgetItem(value))
        self.summary_table.resizeColumnsToContents()

    # ---------------- Експорт / збереження ----------------

    def _ensure_data(self) -> bool:
        if self._agg is None or not self._results:
            QMessageBox.information(self, "Результати", "Немає даних для експорту.")
            return False
        return True

    def _export_csv(self) -> None:
        if not self._ensure_data():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Експорт CSV", "qabench_results.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            exporter.export_csv(path, self._agg, self._dialogs)
        except OSError as exc:
            QMessageBox.warning(self, "Помилка", f"Не вдалося зберегти CSV: {exc}")
            return
        self.status_label.setText(f"Збережено CSV: {path}")

    def _export_xlsx(self) -> None:
        if not self._ensure_data():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Експорт XLSX", "qabench_results.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        try:
            exporter.export_xlsx(path, self._agg, self._dialogs)
        except OSError as exc:
            QMessageBox.warning(self, "Помилка", f"Не вдалося зберегти XLSX: {exc}")
            return
        self.status_label.setText(f"Збережено XLSX: {path}")

    def _save_run(self, *, auto: bool) -> None:
        if self._agg is None or not self._results:
            if not auto:
                QMessageBox.information(self, "Результати", "Немає даних для збереження.")
            return
        payload = build_run_payload(
            models=self._models,
            prompt_name=self._prompt_name,
            prompt_text=self._prompt_text,
            dialogs=self._dialogs,
            levels=self._levels,
            repeats=getattr(self, "_repeats", 1),
            parallel=getattr(self, "_parallel", 2),
            results=self._results,
        )
        try:
            path = storage.save_run(payload, label=self._prompt_name)
        except OSError as exc:
            self.status_label.setText(f"Помилка збереження прогону: {exc}")
            return
        prefix = "Автозбереження" if auto else "Збережено"
        self.status_label.setText(f"{prefix} прогону: {path}")

    def _open_run(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Відкрити збережений прогін",
            str(config.results_dir()),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            payload = storage.load_run(path)
            parsed = parse_run_payload(payload)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Помилка", f"Не вдалося відкрити прогін: {exc}")
            return
        context = {
            "models": parsed["models"],
            "dialogs": parsed["dialogs"],
            "levels": parsed["levels"],
            "prompt_name": parsed["prompt_name"],
            "prompt_text": parsed["prompt_text"],
            "repeats": parsed["repeats"],
            "parallel": parsed["parallel"],
        }
        self.load(parsed["results"], context, auto_save=False)
        self.status_label.setText(f"Відкрито прогін: {path}")
