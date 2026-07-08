from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot import get_context
from app.keyboards import post_nav
from app.services.media import send_post

router = Router()


@router.message(Command("search"))
async def search_cmd(message: Message) -> None:
    tags = message.text.partition(" ")[2].strip()
    if not tags:
        await message.answer("Введите теги после /search")
        return
    ctx = get_context()
    provider, posts = await ctx.providers.search(tags)
    if not posts:
        await message.answer("Ничего не найдено.")
        return
    post = posts[0]
    await ctx.db.execute(
        "INSERT INTO search_history(user_id, provider, tags, post_id) VALUES (?, ?, ?, ?)",
        (message.from_user.id, provider, tags, post.post_id),
    )
    msg = await send_post(message.bot, message.chat.id, post)
    await msg.edit_reply_markup(reply_markup=post_nav())


@router.callback_query(F.data == "search")
async def search_prompt(call: CallbackQuery) -> None:
    await call.message.edit_text("Отправьте /search теги для поиска.")
    await call.answer()


@router.callback_query(F.data == "random")
async def random_art(call: CallbackQuery) -> None:
    ctx = get_context()
    post = await ctx.providers.random()
    if not post:
        await call.message.edit_text("Не удалось найти случайный арт.")
    else:
        await send_post(call.bot, call.message.chat.id, post)
    await call.answer()
