from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.keyboards import post_keyboard
from app.models import BooruPost
from app.providers.registry import fallback_search
from app.safety import LimitState, can_search, record_search, validate_tags
from app.ui.sessions import SearchSession, callback_sessions, parse_callback
from app.ui.texts import ALL_PROVIDERS_FAILED, SEARCH_PROMPT, SESSION_EXPIRED

router = Router()
limit_states: dict[int, LimitState] = {}
post_cache: dict[tuple[int, str], BooruPost] = {}


class SearchInput(StatesGroup):
    waiting_query = State()


async def require_ready(
    message: Message, db, user_id: int | None = None, username: str | None = None
) -> bool:
    user_id = user_id or message.from_user.id
    username = username if username is not None else message.from_user.username
    await db.upsert_user(user_id, username)
    if not await db.is_confirmed(user_id):
        await message.answer("Сначала открой /start и подтверди 18+.")
        return False
    return True


def caption_for(post: BooruPost) -> str:
    tags = ", ".join(post.tags[:12]) or "—"
    return (
        f"Источник: {post.provider}\n"
        f"ID: {post.post_id}\n"
        f"Rating: {post.rating or 'unknown'}\n"
        f"Теги: {tags}"
    )[:1024]


async def send_post(target: Message, key: str, post: BooruPost, page: int) -> None:
    try:
        await target.answer_photo(
            post.file_url,
            caption=caption_for(post),
            reply_markup=post_keyboard(key, page),
        )
    except Exception:
        await target.answer(
            f"Не удалось отправить изображение. Ссылка: {post.display_url}",
            reply_markup=post_keyboard(key, page),
        )


async def run_search(
    message: Message,
    db,
    settings,
    providers_map,
    query: str,
    page: int = 1,
    *,
    user_id: int | None = None,
    username: str | None = None,
) -> None:
    user_id = user_id or message.from_user.id
    username = username if username is not None else message.from_user.username
    if not await require_ready(message, db, user_id, username):
        return
    ok, blocked = validate_tags(query, user_id=user_id, admin_ids=settings.admin_ids)
    if not ok:
        await message.answer(f"Запрещённые теги: {', '.join(sorted(blocked))}")
        return
    state = limit_states.setdefault(user_id, LimitState())
    allowed, reason = can_search(
        state,
        user_id=user_id,
        admin_ids=settings.admin_ids,
        rate_limit_seconds=settings.rate_limit_seconds,
        daily_limit=settings.daily_limit,
    )
    if not allowed:
        await message.answer(reason)
        return
    provider_name = await db.get_provider(user_id, settings.default_provider)
    ordered = {}
    if provider_name in providers_map:
        ordered[provider_name] = providers_map[provider_name]
    for slug, candidate in providers_map.items():
        ordered.setdefault(slug, candidate)
    provider, posts = await fallback_search(ordered, query, settings.result_limit, page)
    record_search(state)
    await db.add_history(user_id, provider.name if provider else provider_name, query)
    if not posts:
        await message.answer(ALL_PROVIDERS_FAILED)
        return
    post = posts[0]
    session = SearchSession(
        user_id=user_id,
        provider=post.provider,
        query=query,
        page=page,
        current_post_id=post.post_id,
        results=posts,
    )
    key = callback_sessions.create(session)
    post_cache[(user_id, post.post_id)] = post
    await send_post(message, key, post, page)


@router.message(Command("search"))
async def search(message: Message, db, settings, providers_map, state: FSMContext) -> None:
    query = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if not query:
        await state.set_state(SearchInput.waiting_query)
        await message.answer(SEARCH_PROMPT)
        return
    await run_search(message, db, settings, providers_map, query)


@router.callback_query(lambda c: c.data == "search_input")
async def search_button(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchInput.waiting_query)
    await callback.message.answer(SEARCH_PROMPT)
    await callback.answer()


@router.message(SearchInput.waiting_query, F.text)
async def search_text(message: Message, db, settings, providers_map, state: FSMContext) -> None:
    await state.clear()
    await run_search(message, db, settings, providers_map, message.text.strip())


@router.message(Command("random"))
async def random_post(message: Message, db, settings, providers_map) -> None:
    await run_search(message, db, settings, providers_map, "rating:explicit")


@router.callback_query(lambda c: c.data == "random")
async def random_button(callback: CallbackQuery, db, settings, providers_map) -> None:
    await run_search(
        callback.message,
        db,
        settings,
        providers_map,
        "rating:explicit",
        user_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith(("next:", "prev:", "repeat:")))
async def page_or_repeat(callback: CallbackQuery, db, settings, providers_map) -> None:
    parsed = parse_callback(callback.data)
    if not parsed:
        await callback.answer("Кнопка устарела. Открой меню заново.", show_alert=True)
        return
    action, key = parsed
    session = callback_sessions.get(key, callback.from_user.id)
    if not session:
        await callback.answer(SESSION_EXPIRED, show_alert=True)
        return
    page = session.page
    if action == "next":
        page += 1
    elif action == "prev":
        page = max(1, page - 1)
    elif action == "repeat":
        page = session.page
    await db.set_provider(callback.from_user.id, session.provider)
    await run_search(
        callback.message,
        db,
        settings,
        providers_map,
        session.query,
        page,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
    )
    await callback.answer()
