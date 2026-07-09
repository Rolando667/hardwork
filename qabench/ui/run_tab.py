"""Вкладка «Запуск»: вибір моделей/рівнів/діалогів/промта і запуск прогону."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core import runner, storage
from core.models import LEVELS, Dialog, RunCell

from .run_worker import RunWorker
from .state import AppState


class RunTab(QWidget):
    run_finished = Signal(object, object)  # (results: List[RunCell], context: dict)

    def __init__(self, state: AppState, parent=None) -> None:
        super().__init__(parent)
        self.state = state
        self._worker: RunWorker | None = None
        self._results: List[RunCell] = []
        self._dialogs: List[Dialog] = []
        self._model_checks: Dict[str, QCheckBox] = {}
        self._dialog_checks: Dict[str, QCheckBox] = {}
        self._level_checks: Dict[str, QCheckBox] = {}
        self._prompts_cache = {}

        # --- Моделі ---
        self.models_box = QVBoxLayout()
        models_container = QWidget()
        models_container.setLayout(self.models_box)
        models_scroll = QScrollArea()
        models_scroll.setWidgetResizable(True)
        models_scroll.setWidget(models_container)
        models_group = QGroupBox("Моделі")
        mg = QVBoxLayout(models_group)
        mg.addWidget(models_scroll)

        # --- Рівні роздумів ---
        levels_group = QGroupBox("Рівні роздумів")
        lg = QVBoxLayout(levels_group)
        for level in LEVELS:
            cb = QCheckBox(level)
            cb.stateChanged.connect(self._update_estimate)
            self._level_checks[level] = cb
            lg.addWidget(cb)
        lg.addStretch()

        # --- Параметри ---
        params_group = QGroupBox("Параметри")
        pg = QVBoxLayout(params_group)
        pg.addWidget(QLabel("Промт (системна інструкція):"))
        self.prompt_combo = QComboBox()
        pg.addWidget(self.prompt_combo)
        rep_row = QHBoxLayout()
        rep_row.addWidget(QLabel("Повторів на комбінацію:"))
        self.repeats_spin = QSpinBox()
        self.repeats_spin.setRange(1, 5)
        self.repeats_spin.setValue(1)
        self.repeats_spin.valueChanged.connect(self._update_estimate)
        rep_row.addWidget(self.repeats_spin)
        rep_row.addStretch()
        pg.addLayout(rep_row)
        par_row = QHBoxLayout()
        par_row.addWidget(QLabel("Паралельних запитів:"))
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 4)
        self.parallel_spin.setValue(2)
        par_row.addWidget(self.parallel_spin)
        par_row.addStretch()
        pg.addLayout(par_row)
        pg.addStretch()

        # --- Діалоги ---
        self.dialogs_box = QVBoxLayout()
        dialogs_container = QWidget()
        dialogs_container.setLayout(self.dialogs_box)
        dialogs_scroll = QScrollArea()
        dialogs_scroll.setWidgetResizable(True)
        dialogs_scroll.setWidget(dialogs_container)
        dialogs_group = QGroupBox("Діалоги")
        dg = QVBoxLayout(dialogs_group)
        self.select_all_cb = QCheckBox("Обрати всі")
        self.select_all_cb.stateChanged.connect(self._toggle_all_dialogs)
        dg.addWidget(self.select_all_cb)
        dg.addWidget(dialogs_scroll)

        top = QHBoxLayout()
        left_col = QVBoxLayout()
        left_col.addWidget(models_group, 2)
        left_col.addWidget(levels_group, 1)
        top.addLayout(left_col, 2)
        top.addWidget(params_group, 2)
        top.addWidget(dialogs_group, 2)

        # --- Оцінка та керування ---
        self.estimate_label = QLabel("Буде викликів: 0")
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("warning")

        self.start_btn = QPushButton("Старт")
        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        self.stop_btn.clicked.connect(self._stop)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addStretch()

        self.progress = QProgressBar()
        self.progress.setFormat("%v з %m")
        self.progress.setValue(0)
        self.progress.setMaximum(1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Лог помилок…")
        self.log.setMaximumHeight(160)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        est_row = QHBoxLayout()
        est_row.addWidget(self.estimate_label)
        est_row.addSpacing(20)
        est_row.addWidget(self.warning_label)
        est_row.addStretch()
        layout.addLayout(est_row)
        layout.addLayout(btn_row)
        layout.addWidget(self.progress)
        layout.addWidget(QLabel("Лог помилок:"))
        layout.addWidget(self.log)

        self.refresh()
        self._restore_selection()

    # ---------------- Оновлення списків ----------------

    def refresh(self) -> None:
        self._rebuild_models()
        self._rebuild_dialogs()
        self._rebuild_prompts()
        self._update_estimate()

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _rebuild_models(self) -> None:
        checked = {mid for mid, cb in self._model_checks.items() if cb.isChecked()}
        self._clear_layout(self.models_box)
        self._model_checks.clear()
        for model in self.state.models:
            cb = QCheckBox(f"{model.name}  ({model.provider} · {model.model_id})")
            cb.setChecked(model.id in checked)
            cb.stateChanged.connect(self._update_estimate)
            self._model_checks[model.id] = cb
            self.models_box.addWidget(cb)
        self.models_box.addStretch()
        if not self.state.models:
            self.models_box.addWidget(QLabel("Немає моделей — додайте на вкладці «Моделі»."))

    def _rebuild_dialogs(self) -> None:
        checked = {did for did, cb in self._dialog_checks.items() if cb.isChecked()}
        self._clear_layout(self.dialogs_box)
        self._dialog_checks.clear()
        self._dialogs = storage.list_dialogs()
        for dialog in self._dialogs:
            suffix = "" if dialog.etalon == "—" else f"  ⟨еталон: {dialog.etalon}⟩"
            cb = QCheckBox(f"{dialog.name}{suffix}")
            cb.setChecked(dialog.id in checked)
            cb.stateChanged.connect(self._update_estimate)
            self._dialog_checks[dialog.id] = cb
            self.dialogs_box.addWidget(cb)
        self.dialogs_box.addStretch()
        if not self._dialogs:
            self.dialogs_box.addWidget(
                QLabel("Немає діалогів — додайте на вкладці «Діалоги».")
            )

    def _rebuild_prompts(self) -> None:
        current = self.prompt_combo.currentText()
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        self._prompts_cache = {}
        for prompt in storage.list_prompts():
            self.prompt_combo.addItem(prompt.name)
            self._prompts_cache[prompt.name] = prompt.text
        idx = self.prompt_combo.findText(current)
        if idx >= 0:
            self.prompt_combo.setCurrentIndex(idx)
        self.prompt_combo.blockSignals(False)

    def _toggle_all_dialogs(self, _state) -> None:
        checked = self.select_all_cb.isChecked()
        for cb in self._dialog_checks.values():
            cb.setChecked(checked)

    # ---------------- Оцінка ----------------

    def _selected_models(self):
        return [
            m
            for m in self.state.models
            if self._model_checks.get(m.id) and self._model_checks[m.id].isChecked()
        ]

    def _selected_levels(self) -> List[str]:
        return [lvl for lvl, cb in self._level_checks.items() if cb.isChecked()]

    def _selected_dialogs(self) -> List[Dialog]:
        ids = {did for did, cb in self._dialog_checks.items() if cb.isChecked()}
        return [d for d in self._dialogs if d.id in ids]

    def _update_estimate(self) -> None:
        models = self._selected_models()
        levels = self._selected_levels()
        dialogs = self._selected_dialogs()
        repeats = self.repeats_spin.value()
        n = runner.count_calls(models, levels, dialogs, repeats)
        self.estimate_label.setText(f"Буде викликів: {n}")
        if n > 200:
            self.warning_label.setText(f"⚠ Увага: {n} викликів (> 200) — це може бути дорого й довго.")
        else:
            self.warning_label.setText("")

    # ---------------- Запуск ----------------

    def _restore_selection(self) -> None:
        sel = self.state.last_selection
        for mid in sel.get("models", []):
            if mid in self._model_checks:
                self._model_checks[mid].setChecked(True)
        for lvl in sel.get("levels", []):
            if lvl in self._level_checks:
                self._level_checks[lvl].setChecked(True)
        for did in sel.get("dialogs", []):
            if did in self._dialog_checks:
                self._dialog_checks[did].setChecked(True)
        prompt = sel.get("prompt", "")
        idx = self.prompt_combo.findText(prompt)
        if idx >= 0:
            self.prompt_combo.setCurrentIndex(idx)
        self.repeats_spin.setValue(int(sel.get("repeats", 1) or 1))
        self.parallel_spin.setValue(int(sel.get("parallel", 2) or 2))
        self._update_estimate()

    def _save_selection(self) -> None:
        sel = self.state.last_selection
        sel["models"] = [m.id for m in self._selected_models()]
        sel["levels"] = self._selected_levels()
        sel["dialogs"] = [d.id for d in self._selected_dialogs()]
        sel["prompt"] = self.prompt_combo.currentText()
        sel["repeats"] = self.repeats_spin.value()
        sel["parallel"] = self.parallel_spin.value()
        self.state.save()

    def _start(self) -> None:
        models = self._selected_models()
        levels = self._selected_levels()
        dialogs = self._selected_dialogs()
        repeats = self.repeats_spin.value()
        parallel = self.parallel_spin.value()
        prompt_name = self.prompt_combo.currentText()
        prompt_text = self._prompts_cache.get(prompt_name, "")

        if not models:
            QMessageBox.warning(self, "Запуск", "Оберіть хоча б одну модель.")
            return
        if not levels:
            QMessageBox.warning(self, "Запуск", "Оберіть хоча б один рівень роздумів.")
            return
        if not dialogs:
            QMessageBox.warning(self, "Запуск", "Оберіть хоча б один діалог.")
            return
        if not prompt_name:
            QMessageBox.warning(self, "Запуск", "Оберіть промт.")
            return
        missing = [m.name for m in models if not m.api_key.strip()]
        if missing:
            QMessageBox.warning(
                self, "Запуск", "Немає API-ключа для моделей: " + ", ".join(missing)
            )
            return

        self._save_selection()
        self._results = []
        n = runner.count_calls(models, levels, dialogs, repeats)
        self.progress.setMaximum(n)
        self.progress.setValue(0)
        self.log.clear()

        self._context = {
            "models": models,
            "levels": levels,
            "dialogs": dialogs,
            "prompt_name": prompt_name,
            "prompt_text": prompt_text,
            "repeats": repeats,
            "parallel": parallel,
        }

        self._worker = RunWorker(
            models=models,
            prompt_text=prompt_text,
            dialogs=dialogs,
            levels=levels,
            repeats=repeats,
            parallel=parallel,
            proxy=self.state.proxy,
            reasoning_map=self.state.reasoning_map,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.result.connect(self._on_result)
        self._worker.log.connect(self._on_log)
        self._worker.finished_run.connect(self._on_finished)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._worker.start()

    def _stop(self) -> None:
        if self._worker is not None:
            self.stop_btn.setEnabled(False)
            self._on_log("Скасування…")
            self._worker.stop()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setMaximum(total)
        self.progress.setValue(done)

    def _on_result(self, cell: RunCell) -> None:
        self._results.append(cell)

    def _on_log(self, message: str) -> None:
        self.log.appendPlainText(message)

    def _on_finished(self) -> None:
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._on_log(f"Готово. Отримано результатів: {len(self._results)}.")
        if self._results:
            self.run_finished.emit(list(self._results), dict(self._context))
        self._worker = None
