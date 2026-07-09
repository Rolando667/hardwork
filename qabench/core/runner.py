"""Async-оркестрація прогону: усі комбінації модель×рівень×діалог×повтор."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

import httpx

from .models import Dialog, ModelConfig, RunCell


ResultCallback = Callable[[RunCell], None]
ProgressCallback = Callable[[int, int], None]


def count_calls(
    models: List[ModelConfig],
    levels: List[str],
    dialogs: List[Dialog],
    repeats: int,
) -> int:
    """Кількість викликів: моделі × рівні × діалоги × повтори."""
    return len(models) * len(levels) * len(dialogs) * max(1, repeats)


async def run_all(
    *,
    models: List[ModelConfig],
    prompt_text: str,
    dialogs: List[Dialog],
    levels: List[str],
    repeats: int,
    parallel: int,
    proxy: str,
    reasoning_map: Dict[str, Any],
    on_result: ResultCallback,
    on_progress: ProgressCallback,
    on_log: Callable[[str], None],
) -> None:
    """Виконати всі комбінації, викликаючи колбеки з головного (worker) потоку.

    Скасування виконується скасуванням завдання ззовні (worker.stop()).
    """
    # Пізній імпорт, щоб уникнути циклічної залежності на рівні модуля.
    from providers import get_provider

    total = count_calls(models, levels, dialogs, repeats)
    done = 0
    lock = asyncio.Lock()
    sem = asyncio.Semaphore(max(1, parallel))

    timeout = httpx.Timeout(120.0)
    client_kwargs: Dict[str, Any] = {"timeout": timeout}
    if proxy:
        client_kwargs["proxy"] = proxy

    async def unit(model: ModelConfig, level: str, dialog: Dialog, rep: int) -> None:
        nonlocal done
        async with sem:
            try:
                provider = get_provider(model.provider)
                cell = await provider(
                    client,
                    model,
                    prompt_text,
                    dialog.text,
                    level,
                    reasoning_map,
                    dialog_id=dialog.id,
                    repeat_index=rep,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # непередбачена помилка → клітинка з ⚠️
                cell = RunCell(
                    dialog_id=dialog.id,
                    model_id=model.id,
                    level=level,
                    repeat_index=rep,
                    error=f"внутрішня помилка: {exc}",
                )
                on_log(
                    f"Помилка [{model.name} @ {level} / {dialog.name} #{rep + 1}]: {exc}"
                )
            async with lock:
                done += 1
                current = done
            on_result(cell)
            on_progress(current, total)
            if cell.error:
                on_log(
                    f"⚠️ {model.name} @ {level} / {dialog.name} #{rep + 1}: {cell.error}"
                )

    async with httpx.AsyncClient(**client_kwargs) as client:
        tasks: List[asyncio.Task] = []
        for model in models:
            for level in levels:
                for dialog in dialogs:
                    for rep in range(max(1, repeats)):
                        tasks.append(asyncio.ensure_future(unit(model, level, dialog, rep)))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            # Дочекатися завершення скасування, не падаючи.
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
