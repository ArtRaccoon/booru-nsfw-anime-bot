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
from app.providers.prober import probe_candidate
from app.providers.registry import engine_class
from app.safety import is_admin

router = Router()


class CatalogFSM(StatesGroup):
    info = State()
    enable = State()
    disable = State()


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
        await message.answer(f"Не удалось загрузить каталог: {type(exc).__name__}")


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
    result = await probe_candidate(
        row["base_url"],
        row["engine"],
        proxy_url=settings.proxy_url,
        timeout=settings.booru_catalog_timeout_seconds,
        user_agent=settings.booru_user_agent,
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


@router.message(Command("catalog_check_all"))
async def catalog_check_all(message: Message, db, settings) -> None:
    if not await require_admin(message, settings):
        return
    rows = await db.list_provider_candidates(limit=10000)
    sem = asyncio.Semaphore(max(1, settings.booru_catalog_probe_concurrency))
    counts = {}
    done = 0
    progress = await message.answer(f"Проверяю источники: 0/{len(rows)}...")

    async def one(row):
        nonlocal done
        async with sem:
            st = await _probe_row(db, row, settings)
            counts[st] = counts.get(st, 0) + 1
            done += 1
            if done % 10 == 0 or done == len(rows):
                with suppress(Exception):
                    await progress.edit_text(f"Проверяю источники: {done}/{len(rows)}...")

    await asyncio.gather(*(one(r) for r in rows))
    available = await db.list_provider_candidates(status="available", limit=200)
    await message.answer(
        "Итог проверки:\n" + "\n".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    )
    for i in range(0, len(available), 30):
        await message.answer("Доступные:\n" + rows_text(available[i : i + 30]))


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
async def catalog_buttons(callback: CallbackQuery, db, settings, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id, settings.admin_ids):
        await callback.answer("Admin only", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]
    if action == "import":
        await catalog_import(callback.message, db, settings)
    elif action == "check_all":
        await catalog_check_all(callback.message, db, settings)
    elif action == "available":
        await callback.message.answer(rows_text(await db.list_provider_candidates("available", 40)))
    elif action == "unchecked":
        await callback.message.answer(rows_text(await db.list_provider_candidates("unchecked", 40)))
    elif action == "broken":
        await callback.message.answer(rows_text(await db.list_provider_candidates("broken", 40)))
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
