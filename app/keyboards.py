from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def age_gate_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="I am 18+", callback_data="age:confirm")]]
    )


def post_keyboard(query: str, page: int, provider: str, post_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Next", callback_data=f"next:{provider}:{page + 1}:{query}"
                ),
                InlineKeyboardButton(text="Repeat", callback_data=f"repeat:{provider}:{query}"),
                InlineKeyboardButton(text="Save", callback_data=f"fav:{provider}:{post_id}"),
            ]
        ]
    )


def providers_keyboard(providers: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=p, callback_data=f"provider:{p}")] for p in providers
        ]
    )
