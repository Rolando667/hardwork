"""Агрегація результатів у зведену таблицю та підсумки по колонках."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import (
    Dialog,
    ModelConfig,
    RunCell,
    V_DASH,
    V_FAIL,
    V_OK,
    VERDICTS,
)


ColumnKey = Tuple[str, str]  # (model_id, level)


@dataclass
class Column:
    model_id: str
    level: str
    model_name: str
    label: str  # "модель @ рівень"


@dataclass
class CellAgg:
    majority_status: Optional[str] = None   # мажоритарний вердикт або None
    n_total: int = 0                        # усього прогонів у клітинці
    n_majority: int = 0                     # скільки прогонів дали мажоритарний вердикт
    instable: bool = False                  # прогони розійшлися
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost: Optional[float] = None
    avg_seconds: float = 0.0
    comment: str = ""
    raw: str = ""                           # усі сирі відповіді
    translation: str = ""
    error: Optional[str] = None             # якщо жоден прогін не дав вердикту
    color: Optional[str] = None             # "green" / "red" / None


@dataclass
class ColumnSummary:
    matches: int = 0        # збігів з еталоном
    false_alerts: int = 0   # хибних алертів (еталон OK, модель FAIL)
    misses: int = 0         # пропусків (еталон FAIL, модель OK)
    cost: float = 0.0       # сумарна вартість колонки
    avg_time: float = 0.0   # середній час на запит


@dataclass
class Aggregation:
    columns: List[Column] = field(default_factory=list)
    cells: Dict[Tuple[str, str, str], CellAgg] = field(default_factory=dict)
    col_summary: Dict[ColumnKey, ColumnSummary] = field(default_factory=dict)
    total_cost: float = 0.0


def _fraction(cell: CellAgg) -> str:
    """Позначка нестабільності на кшталт «2/3»."""
    if cell.n_total > 1 and cell.instable and cell.n_majority:
        return f"{cell.n_majority}/{cell.n_total}"
    return ""


def cell_display(cell: CellAgg) -> str:
    """Текст для клітинки (без дрібних метрик): іконка + позначка нестабільності."""
    from .models import ERROR_ICON, VERDICT_ICON

    if cell.majority_status is None:
        return ERROR_ICON
    icon = VERDICT_ICON.get(cell.majority_status, ERROR_ICON)
    frac = _fraction(cell)
    return f"{icon} {frac}".strip()


def aggregate(
    results: List[RunCell],
    models: List[ModelConfig],
    levels: List[str],
    dialogs: List[Dialog],
) -> Aggregation:
    """Побудувати зведення. Порядок колонок = моделі × рівні (як обрано)."""
    agg = Aggregation()
    dialog_by_id = {d.id: d for d in dialogs}
    model_by_id = {m.id: m for m in models}

    # Колонки у порядку модель→рівень.
    for model in models:
        for level in levels:
            agg.columns.append(
                Column(
                    model_id=model.id,
                    level=level,
                    model_name=model.name,
                    label=f"{model.name} @ {level}",
                )
            )
            agg.col_summary[(model.id, level)] = ColumnSummary()

    # Групування прогонів у клітинки.
    grouped: Dict[Tuple[str, str, str], List[RunCell]] = {}
    for cell in results:
        key = (cell.dialog_id, cell.model_id, cell.level)
        grouped.setdefault(key, []).append(cell)

    time_acc: Dict[ColumnKey, List[float]] = {}

    for key, runs in grouped.items():
        dialog_id, model_id, level = key
        col_key = (model_id, level)
        c = CellAgg()
        c.n_total = len(runs)

        verdict_counts: Counter = Counter()
        tokens_in = 0
        have_in = False
        tokens_out = 0
        have_out = False
        cost_sum = 0.0
        have_cost = False
        seconds: List[float] = []
        raw_parts: List[str] = []
        comments_by_verdict: Dict[str, str] = {}

        for r in runs:
            seconds.append(r.seconds)
            if r.tokens_in is not None:
                tokens_in += r.tokens_in
                have_in = True
            if r.tokens_out is not None:
                tokens_out += r.tokens_out
                have_out = True
            if r.cost is not None:
                cost_sum += r.cost
                have_cost = True
            if r.translation and not c.translation:
                c.translation = r.translation
            header = f"[#{r.repeat_index + 1}]"
            if r.error:
                raw_parts.append(f"{header} ПОМИЛКА: {r.error}\n{r.raw}".rstrip())
            else:
                raw_parts.append(f"{header} {r.raw}".rstrip())
            if r.status in VERDICTS:
                verdict_counts[r.status] += 1
                comments_by_verdict.setdefault(r.status, r.comment)

        c.tokens_in = tokens_in if have_in else None
        c.tokens_out = tokens_out if have_out else None
        c.cost = cost_sum if have_cost else None
        c.avg_seconds = sum(seconds) / len(seconds) if seconds else 0.0
        c.raw = "\n\n".join(raw_parts)

        if verdict_counts:
            majority, n_maj = verdict_counts.most_common(1)[0]
            c.majority_status = majority
            c.n_majority = n_maj
            n_verdicts = sum(verdict_counts.values())
            c.instable = len(verdict_counts) > 1
            c.comment = comments_by_verdict.get(majority, "")
        else:
            # Жоден прогін не дав вердикту — суто помилкова клітинка.
            first_err = next((r.error for r in runs if r.error), "помилка")
            c.error = first_err

        # Підсвітка за еталоном.
        dialog = dialog_by_id.get(dialog_id)
        if (
            dialog is not None
            and dialog.etalon in VERDICTS
            and c.majority_status is not None
        ):
            c.color = "green" if c.majority_status == dialog.etalon else "red"

        agg.cells[key] = c

        # Підсумки по колонці.
        summary = agg.col_summary.get(col_key)
        if summary is not None:
            if c.cost is not None:
                summary.cost += c.cost
            time_acc.setdefault(col_key, []).extend(seconds)
            if (
                dialog is not None
                and dialog.etalon in VERDICTS
                and c.majority_status is not None
            ):
                if c.majority_status == dialog.etalon:
                    summary.matches += 1
                if dialog.etalon == V_OK and c.majority_status == V_FAIL:
                    summary.false_alerts += 1
                if dialog.etalon == V_FAIL and c.majority_status == V_OK:
                    summary.misses += 1

    for col_key, summary in agg.col_summary.items():
        times = time_acc.get(col_key, [])
        summary.avg_time = sum(times) / len(times) if times else 0.0
        agg.total_cost += summary.cost

    return agg
