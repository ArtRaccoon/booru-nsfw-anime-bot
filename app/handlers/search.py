from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.keyboards import post_keyboard
from app.models import BooruPost
from app.providers.registry import fallback_search
from app.safety import LimitState, can_search, record_search, validate_tags

router = Router()
limit_states: dict[int, LimitState] = {}
post_cache: dict[tuple[int, str], BooruPost] = {}


async def require_ready(message: Message, db) -> bool:
    await db.upsert_user(message.from_user.id, message.from_user.username)
    if not await db.is_confirmed(message.from_user.id):
        await message.answer("Please use /start and confirm you are 18+ first.")
        return False
    return True


async def send_post(target: Message, post: BooruPost, query: str, page: int) -> None:
    caption = (
        f"{post.provider} #{post.post_id}\n"
        f"Rating: {post.rating or 'unknown'}\n"
        f"Tags: {' '.join(post.tags[:12])}"
    )
    try:
        await target.answer_photo(
            post.file_url,
            caption=caption[:1024],
            reply_markup=post_keyboard(query, page, post.provider, post.post_id),
        )
    except Exception:
        await target.answer(
            f"Image could not be sent. Source: {post.display_url}",
            reply_markup=post_keyboard(query, page, post.provider, post.post_id),
        )


async def run_search(
    message: Message, db, settings, providers_map, query: str, page: int = 1
) -> None:
    if not await require_ready(message, db):
        return
    ok, blocked = validate_tags(query, user_id=message.from_user.id, admin_ids=settings.admin_ids)
    if not ok:
        await message.answer(f"Blocked tags are not allowed: {', '.join(sorted(blocked))}")
        return
    state = limit_states.setdefault(message.from_user.id, LimitState())
    allowed, reason = can_search(
        state,
        user_id=message.from_user.id,
        admin_ids=settings.admin_ids,
        rate_limit_seconds=settings.rate_limit_seconds,
        daily_limit=settings.daily_limit,
    )
    if not allowed:
        await message.answer(reason)
        return
    provider_name = await db.get_provider(message.from_user.id, settings.default_provider)
    ordered = {}
    if provider_name in providers_map:
        ordered[provider_name] = providers_map[provider_name]
    for slug, candidate in providers_map.items():
        ordered.setdefault(slug, candidate)
    provider, posts = await fallback_search(ordered, query, settings.result_limit, page)
    record_search(state)
    await db.add_history(message.from_user.id, provider.name if provider else provider_name, query)
    if not posts:
        await message.answer("No results.")
        return
    post_cache[(message.from_user.id, posts[0].post_id)] = posts[0]
    await send_post(message, posts[0], query, page)


@router.message(Command("search"))
async def search(message: Message, db, settings, providers_map) -> None:
    query = message.text.split(maxsplit=1)[1].strip() if len(message.text.split()) > 1 else ""
    if not query:
        await message.answer("Usage: /search <tags>")
        return
    await run_search(message, db, settings, providers_map, query)


@router.message(Command("random"))
async def random_post(message: Message, db, settings, providers_map) -> None:
    await run_search(message, db, settings, providers_map, "rating:explicit")


@router.callback_query(lambda c: c.data.startswith(("next:", "repeat:")))
async def next_or_repeat(callback: CallbackQuery, db, settings, providers_map) -> None:
    parts = callback.data.split(":", 3)
    if parts[0] == "next":
        _, provider, page, query = parts
        await db.set_provider(callback.from_user.id, provider)
        await run_search(callback.message, db, settings, providers_map, query, int(page))
    else:
        _, provider, query = parts
        await db.set_provider(callback.from_user.id, provider)
        await run_search(callback.message, db, settings, providers_map, query)
