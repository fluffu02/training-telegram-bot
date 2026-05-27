from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def daily_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data="daily:done"),
                InlineKeyboardButton(text="⏭ Пропустить", callback_data="daily:skip"),
            ]
        ]
    )


def weekly_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚖️ Записать вес", callback_data="weekly:weight_help")],
            [InlineKeyboardButton(text="📷 Отправить фото", callback_data="weekly:photo_help")],
        ]
    )
