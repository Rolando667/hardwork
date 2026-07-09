"""Фоновий потік прогону (QThread), що керує asyncio-циклом і викликами API."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from PySide6.QtCore import QThread, Signal

from core import runner
from core.models import Dialog, ModelConfig, RunCell


class RunWorker(QThread):
    progress = Signal(int, int)      # (виконано, усього)
    result = Signal(object)          # RunCell
    log = Signal(str)
    finished_run = Signal()

    def __init__(
        self,
        *,
        models: List[ModelConfig],
        prompt_text: str,
        dialogs: List[Dialog],
        levels: List[str],
        repeats: int,
        parallel: int,
        proxy: str,
        reasoning_map: Dict[str, Any],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._models = models
        self._prompt_text = prompt_text
        self._dialogs = dialogs
        self._levels = levels
        self._repeats = repeats
        self._parallel = parallel
        self._proxy = proxy
        self._reasoning_map = reasoning_map
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    def run(self) -> None:  # виконується у фоновому потоці
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            self._task = loop.create_task(self._main())
            loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            self.log.emit("Прогін скасовано користувачем.")
        except Exception as exc:  # захист від падіння потоку
            self.log.emit(f"Критична помилка прогону: {exc}")
        finally:
            try:
                loop.close()
            except Exception:
                pass
            self.finished_run.emit()

    async def _main(self) -> None:
        await runner.run_all(
            models=self._models,
            prompt_text=self._prompt_text,
            dialogs=self._dialogs,
            levels=self._levels,
            repeats=self._repeats,
            parallel=self._parallel,
            proxy=self._proxy,
            reasoning_map=self._reasoning_map,
            on_result=lambda c: self.result.emit(c),
            on_progress=lambda d, t: self.progress.emit(d, t),
            on_log=lambda s: self.log.emit(s),
        )

    def stop(self) -> None:
        """Коректно скасувати прогін із головного потоку."""
        loop = self._loop
        task = self._task
        if loop is not None and task is not None:
            loop.call_soon_threadsafe(task.cancel)
