from __future__ import annotations

import asyncio
from contextlib import suppress

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.keyboards import catalog_keyboard
from app.providers.catalog import fetch_catalog
from app.providers.prober import ProbeResult, probe_candidate
from app.providers.registry import engine_class
from app.safety import is_admin

router = Router()

RETRYABLE_STATUSES = ("unchecked", "timeout", "error", "invalid_response")
CATALOG_BATCH_DEFAULT = 25
CATALOG_BATCH_MAX = 50
catalog_check_running = False
catalog_check_stop_event = asyncio.Event()


class CatalogFSM(StatesGroup):
    info = State()
    enable = State()
    disable = State()
    engine = State()
    status = State()


def _arg(message: Message) -> str:
    return message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""


async def require_admin(message: Message, settings) -> bool:
    if not is_admin(message.from_user.id, settings.admin_ids):
        await message.answer("Admin only.")
        return False
    return True


def counts_text(c: dict) -> str:
    return (
        "🗂 Каталог источников\n\n"
        f"Всего: {c.get('total', 0)}\n"
        f"Доступных: {c.get('available', 0)}\n"
        f"Включено: {c.get('enabled', 0)}\n"
        f"Непроверенных: {c.get('unchecked', 0)}\n"
        f"Сломанных: {c.get('broken', 0)}\n"
        f"Auth: {c.get('auth_required', 0)}\n"
        f"No API: {c.get('no_api', 0)}"
    )


def rows_text(rows) -> str:
    return (
        "\n".join(
            " | ".join(
                (r["slug"], r["engine"] or "unknown", r["availability_status"], r["base_url"])
            )
            for r in rows
        )
        or "Нет данных."
    )


def _limit(
    raw: str, default: int = CATALOG_BATCH_DEFAULT, max_limit: int = CATALOG_BATCH_MAX
) -> int:
    try:
        return min(max(1, int(raw)), max_limit) if raw else default
    except ValueError:
        return default


def _check_summary(counts: dict[str, int], checked: int, remaining: int) -> str:
    return (
        f"Проверено: {checked}\n"
        f"Доступных: {counts.get('available', 0)}\n"
        f"Timeout: {counts.get('timeout', 0)}\n"
        f"No API: {counts.get('no_api', 0)}\n"
        f"Auth: {counts.get('auth_required', 0)}\n"
        f"Broken: {counts.get('broken', 0)}\n"
        f"Осталось непроверенных: {remaining}"
    )


def report_text(report: dict) -> str:
    counts = report["counts"]
    by_status = (
        ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()) if k not in {"total", "enabled"})
        or "нет"
    )
    by_engine = ", ".join(f"{k}: {v}" for k, v in list(report["by_engine"].items())[:10]) or "нет"
    top = ", ".join(f"{k}: {v}" for k, v in report["top_available_engines"].items()) or "нет"
    return (
        "📊 Отчёт каталога\n\n"
        f"Всего: {counts.get('total', 0)}\n"
        f"Включено: {counts.get('enabled', 0)}\n"
        f"По статусам: {by_status}\n"
        f"По движкам: {by_engine}\n"
        f"Топ доступных движков: {top}"
    )


async def _run_catalog_check(message: Message, db, settings, rows, remaining_filter) -> None:
    global catalog_check_running
    if catalog_check_running:
        await message.answer("Проверка уже идёт. Дождись завершения.")
        return
    catalog_check_running = True
    catalog_check_stop_event.clear()
    counts: dict[str, int] = {}
    done = 0
    total = len(rows)
    progress = await message.answer(f"🧪 Проверяю источники: 0/{total}")
    sem = asyncio.Semaphore(max(1, settings.booru_catalog_probe_concurrency))

    async def one(row):
        nonlocal done
        if catalog_check_stop_event.is_set():
            return
        async with sem:
            if catalog_check_stop_event.is_set():
                return
            st = await _probe_row(db, row, settings)
            counts[st] = counts.get(st, 0) + 1
            done += 1
            if done % 5 == 0 or done == total:
                with suppress(Exception):
                    await progress.edit_text(f"🧪 Проверяю источники: {done}/{total}")

    try:
        await asyncio.gather(*(one(r) for r in rows))
        remaining = await db.count_provider_candidates_for_check(**remaining_filter)
        text = _check_summary(counts, done, remaining)
        if catalog_check_stop_event.is_set():
            text = "Проверка остановлена. Уже сохранённые результаты не потеряны.\n" + text
        await progress.edit_text(text)
    finally:
        catalog_check_running = False
        catalog_check_stop_event.clear()


async def _check_batch(
    message: Message,
    db,
    settings,
    *,
    statuses=RETRYABLE_STATUSES,
    engine=None,
    limit=CATALOG_BATCH_DEFAULT,
) -> None:
    limit = min(limit, CATALOG_BATCH_MAX)
    rows = await db.list_provider_candidates_for_check(
        statuses=statuses, engine=engine, limit=limit
    )
    if not rows:
        await message.answer("Нет источников для проверки.")
        return
    await _run_catalog_check(message, db, settings, rows, {"statuses": statuses, "engine": engine})


async def reload_registry(provider_registry, providers_map, db):
    await provider_registry.reload(db)
    providers_map.clear()
    providers_map.update(provider_registry.providers)


@router.message(Command("catalog_import"))
async def catalog_import(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    try:
        entries = await fetch_catalog(
            settings.booru_catalog_source_url,
            proxy_url=settings.proxy_url,
            user_agent=settings.booru_user_agent,
        )
        summary = await db.upsert_provider_candidates(entries)
        counts = {}
        for e in entries:
            counts[e.engine] = counts.get(e.engine, 0) + 1
        text = (
            "Импортировано: {imported}\nОбновлено: {updated}\nВсего: {total}\nEngines: {counts}"
        ).format(**summary, counts=counts)
        await message.answer(text)
    except Exception as exc:
        total = await db.count_provider_candidates()
        if total:
            await message.answer(
                f"Не удалось загрузить каталог: {type(exc).__name__}. "
                f"Продолжаю с локальной базой: {total} кандидатов."
            )
        else:
            await message.answer(
                f"Не удалось загрузить каталог: {type(exc).__name__}. Локальных кандидатов нет."
            )


@router.message(Command("catalog_status"))
async def catalog_status(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await message.answer(
            counts_text(await db.provider_catalog_counts()), reply_markup=catalog_keyboard()
        )


async def _list(message, db, settings, status=None):
    if not await require_admin(message, settings):
        return
    await message.answer(rows_text(await db.list_provider_candidates(status=status, limit=40)))


@router.message(Command("catalog_list"))
async def catalog_list(message, db, settings):
    await _list(message, db, settings)


@router.message(Command("catalog_available"))
async def catalog_available(message, db, settings):
    await _list(message, db, settings, "available")


@router.message(Command("catalog_unchecked"))
async def catalog_unchecked(message, db, settings):
    await _list(message, db, settings, "unchecked")


@router.message(Command("catalog_broken"))
async def catalog_broken(message, db, settings):
    await _list(message, db, settings, "broken")


@router.message(Command("catalog_info"))
async def catalog_info(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    row = await db.get_provider_candidate(_arg(message))
    await message.answer("Не найдено." if not row else "\n".join(f"{k}: {row[k]}" for k in row))


async def _probe_row(db, row, settings):
    try:
        result = await probe_candidate(
            row["base_url"],
            row["engine"],
            proxy_url=settings.proxy_url,
            timeout=settings.booru_catalog_timeout_seconds,
            user_agent=settings.booru_user_agent,
        )
    except Exception as exc:
        result = ProbeResult(
            "error", engine=row["engine"], error=f"{type(exc).__name__}: {exc}"[:500]
        )
    await db.update_candidate_probe(row["slug"], result)
    return result.availability_status


@router.message(Command("catalog_check"))
async def catalog_check(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    row = await db.get_provider_candidate(_arg(message))
    if not row:
        await message.answer("Не найдено.")
        return
    status = await _probe_row(db, row, settings)
    await message.answer(f"{row['slug']}: {status}")


@router.message(Command("catalog_check_batch"))
async def catalog_check_batch(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    await _check_batch(message, db, settings, limit=_limit(_arg(message)))


@router.message(Command("catalog_check_resume"))
async def catalog_check_resume(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    await _check_batch(message, db, settings)


@router.message(Command("catalog_check_stop"))
async def catalog_check_stop(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    if catalog_check_running:
        catalog_check_stop_event.set()
        await message.answer("Проверка остановлена. Уже сохранённые результаты не потеряны.")
    else:
        await message.answer("Сейчас нет активной проверки.")


@router.message(Command("catalog_check_all"))
async def catalog_check_all(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    args = _arg(message).split()
    confirm = bool(args and args[0].lower() == "confirm")
    total = await db.count_provider_candidates_for_check(statuses=RETRYABLE_STATUSES)
    max_run = max(1, settings.booru_catalog_check_all_max)
    if total > max_run and not confirm:
        await message.answer(
            f"Найдено {total} источников. За один запуск проверю максимум {max_run}. "
            "Используй /catalog_check_all confirm чтобы проверить все."
        )
        total = max_run
    rows = await db.list_provider_candidates_for_check(statuses=RETRYABLE_STATUSES, limit=total)
    if not rows:
        await message.answer("Нет источников для проверки.")
        return
    await _run_catalog_check(message, db, settings, rows, {"statuses": RETRYABLE_STATUSES})


@router.message(Command("catalog_check_engine"))
async def catalog_check_engine(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    parts = _arg(message).split()
    if not parts:
        await message.answer("Укажи engine.")
        return
    await _check_batch(
        message, db, settings, engine=parts[0], limit=_limit(parts[1] if len(parts) > 1 else "")
    )


@router.message(Command("catalog_check_status"))
async def catalog_check_status(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    parts = _arg(message).split()
    if not parts:
        await message.answer("Укажи status.")
        return
    await _check_batch(
        message,
        db,
        settings,
        statuses=(parts[0],),
        limit=_limit(parts[1] if len(parts) > 1 else ""),
    )


@router.message(Command("catalog_enable_available"))
async def catalog_enable_available(
    message: Message, db, settings, provider_registry, providers_map
) -> None:
    if not await require_admin(message, settings):
        return
    engine = _arg(message) or None
    rows = await db.enable_available_candidates(engine=engine, limit=50)
    await reload_registry(provider_registry, providers_map, db)
    await message.answer("Включено:\n" + rows_text(rows))


@router.message(Command("catalog_report"))
async def catalog_report(message: Message, db, settings) -> None:
    if await require_admin(message, settings):
        await message.answer(report_text(await db.provider_catalog_report()))


@router.message(Command("catalog_available_engine"))
async def catalog_available_engine(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    engine = _arg(message)
    if not engine:
        await message.answer("Укажи engine.")
        return
    rows = await db.list_provider_candidates_for_check(
        statuses=("available",), engine=engine, limit=100
    )
    await message.answer(rows_text(rows))


@router.message(Command("catalog_check_available"))
async def catalog_check_available(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    rows = await db.list_provider_candidates(status="available", limit=10000)
    for r in rows:
        await _probe_row(db, r, settings)
    await message.answer("Доступные/включённые перепроверены.")


@router.message(Command("catalog_enable"))
async def catalog_enable(message: Message, db, settings, provider_registry, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    slug = _arg(message)
    row = await db.get_provider_candidate(slug)
    if not row or row["availability_status"] != "available":
        await message.answer("Источник не доступен; включение отклонено.")
        return
    try:
        engine_class(row["engine"])
    except Exception:
        await message.answer("Нет адаптера для engine; включение отклонено.")
        return
    await db.set_candidate_enabled(slug, True)
    await reload_registry(provider_registry, providers_map, db)
    await message.answer(f"Включён candidate {slug}.")


@router.message(Command("catalog_disable"))
async def catalog_disable(message: Message, db, settings, provider_registry, providers_map) -> None:
    if not await require_admin(message, settings):
        return
    await db.set_candidate_enabled(_arg(message), False)
    await reload_registry(provider_registry, providers_map, db)
    await message.answer("Отключено.")


@router.callback_query(F.data == "admin_catalog")
async def admin_catalog(callback: CallbackQuery, db, settings) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Admin only", show_alert=True)
        return
    await callback.message.edit_text(
        counts_text(await db.provider_catalog_counts()), reply_markup=catalog_keyboard()
    )


@router.callback_query(F.data.startswith("catalog:"))
async def catalog_buttons(
    callback: CallbackQuery,
    db,
    settings,
    state: FSMContext,
    provider_registry=None,
    providers_map=None,
) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Admin only", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]
    if action == "import":
        await catalog_import(callback.message, db, settings)
    elif action in {"check_batch", "resume"}:
        await _check_batch(callback.message, db, settings)
    elif action == "stop":
        catalog_check_stop_event.set()
        await callback.message.answer(
            "Проверка остановлена. Уже сохранённые результаты не потеряны."
        )
    elif action == "report":
        await callback.message.answer(report_text(await db.provider_catalog_report()))
    elif action == "enable_available":
        if provider_registry is None or providers_map is None:
            await callback.message.answer("Используй команду /catalog_enable_available [engine].")
        else:
            rows = await db.enable_available_candidates(limit=50)
            await reload_registry(provider_registry, providers_map, db)
            await callback.message.answer("Включено:\n" + rows_text(rows))
    elif action == "available":
        await callback.message.answer(rows_text(await db.list_provider_candidates("available", 40)))
    elif action == "unchecked":
        await callback.message.answer(rows_text(await db.list_provider_candidates("unchecked", 40)))
    elif action == "broken":
        await callback.message.answer(rows_text(await db.list_provider_candidates("broken", 40)))
    elif action == "engine":
        await state.set_state(CatalogFSM.engine)
        await callback.message.answer("Введите engine:")
    elif action in {"info", "enable", "disable"}:
        await state.set_state(getattr(CatalogFSM, action))
        await callback.message.answer("Введите slug:")


@router.message(CatalogFSM.info)
async def catalog_info_input(message: Message, db, settings, state: FSMContext) -> None:
    if await require_admin(message, settings):
        row = await db.get_provider_candidate((message.text or "").strip())
        await message.answer("Не найдено." if not row else "\n".join(f"{k}: {row[k]}" for k in row))
    await state.clear()


@router.message(CatalogFSM.enable)
async def catalog_enable_input(
    message: Message, db, settings, provider_registry, providers_map, state: FSMContext
) -> None:
    if await require_admin(message, settings):
        slug = (message.text or "").strip()
        row = await db.get_provider_candidate(slug)
        if not row or row["availability_status"] != "available":
            await message.answer("Источник не доступен; включение отклонено.")
        else:
            try:
                engine_class(row["engine"])
            except Exception:
                await message.answer("Нет адаптера для engine; включение отклонено.")
            else:
                await db.set_candidate_enabled(slug, True)
                await reload_registry(provider_registry, providers_map, db)
                await message.answer(f"Включён candidate {slug}.")
    await state.clear()


@router.message(CatalogFSM.disable)
async def catalog_disable_input(
    message: Message, db, settings, provider_registry, providers_map, state: FSMContext
) -> None:
    if await require_admin(message, settings):
        await db.set_candidate_enabled((message.text or "").strip(), False)
        await reload_registry(provider_registry, providers_map, db)
        await message.answer("Отключено.")
    await state.clear()


@router.message(CatalogFSM.engine)
async def catalog_engine_input(message: Message, db, settings, state: FSMContext) -> None:
    if await require_admin(message, settings):
        engine = (message.text or "").strip()
        rows = await db.list_provider_candidates_for_check(
            statuses=("available",), engine=engine, limit=100
        )
        await message.answer(rows_text(rows))
    await state.clear()
