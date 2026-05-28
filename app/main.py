import asyncio
from datetime import date, datetime, timedelta, timezone as utc_timezone
import logging
import os
import sys
from time import perf_counter
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import BotCommand, CallbackQuery, Message, TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import load_settings
from app.db import Database
from app.keyboards import daily_keyboard, weekly_keyboard
from app.program import get_training_for_date, load_program, render_training_message, render_week_message


WEEKDAYS = {
    "monday": "mon",
    "tuesday": "tue",
    "wednesday": "wed",
    "thursday": "thu",
    "friday": "fri",
    "saturday": "sat",
    "sunday": "sun",
}


settings = load_settings()
timezone = ZoneInfo(settings.timezone)
program = load_program(settings.program_path)
db = Database(settings.database_path)
bot = Bot(token=settings.bot_token)
dp = Dispatcher()


def today_local() -> date:
    return datetime.now(timezone).date()


def week_start(target_date: date) -> date:
    return target_date - timedelta(days=target_date.weekday())

def progression_weeks(target_date: date) -> int:
    start_date = date.fromisoformat(settings.program_start_date)
    return max(0, (target_date - start_date).days // 7)


def parse_time(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour), int(minute)


async def log_request(
    message: Message,
    command_type: str,
    started_at: float,
    is_ai_request: bool = False,
    success: bool = True,
    error: str | None = None,
) -> None:
    await db.save_request_log(
        chat_id=message.chat.id,
        user_id=message.from_user.id if message.from_user else None,
        command_type=command_type,
        is_ai_request=is_ai_request,
        duration_seconds=perf_counter() - started_at,
        success=success,
        error=error,
    )


def local_start_as_utc_naive(value: datetime) -> datetime:
    return value.astimezone(utc_timezone.utc).replace(tzinfo=None)

def format_db_datetime(value: str | None, include_time: bool = True) -> str:
    if not value:
        return "—"

    try:
        parsed = datetime.fromisoformat(value).replace(tzinfo=utc_timezone.utc).astimezone(timezone)
    except ValueError:
        return value

    if include_time:
        return parsed.strftime("%d.%m.%Y %H:%M")
    return parsed.strftime("%d.%m.%Y")


def format_compact_datetime(value: str | None) -> str:
    if not value:
        return "—"

    try:
        parsed = datetime.fromisoformat(value).replace(tzinfo=utc_timezone.utc).astimezone(timezone)
    except ValueError:
        return value

    return parsed.strftime("%d.%m %H:%M")


def user_display_name(user: dict) -> str:
    return user.get("first_name") or "—"


def user_username(user: dict) -> str:
    username = user.get("username")
    return f"@{username}" if username else "—"


def render_user_details(users: list[dict]) -> str:
    if not users:
        return "Нет данных."

    blocks = []
    for index, user in enumerate(users, start=1):
        blocks.append(
            f"{index}. Имя: {user_display_name(user)}\n"
            f"   Username: {user_username(user)}\n"
            f"   Telegram ID: {user.get('telegram_id') or '—'}\n"
            f"   Дата первого входа: {format_db_datetime(user.get('first_seen') or user.get('created_at'), include_time=False)}\n"
            f"   Последняя активность: {format_db_datetime(user.get('last_seen') or user.get('created_at'))}\n"
            f"   Сообщений: {user.get('messages_count') or 0}"
        )
    return "\n\n".join(blocks)


def render_compact_users(users: list[dict], start_index: int = 1) -> str:
    if not users:
        return "Нет данных."

    blocks = []
    for index, user in enumerate(users, start=start_index):
        name = user_display_name(user)
        username = user.get("username")
        title = f"👤 {index}. {name}"
        if username:
            title += f" (@{username})"

        messages_count = int(user.get("messages_count") or 0)
        messages_line = "Новый пользователь" if messages_count == 0 else f"Сообщений: {messages_count}"
        telegram_id = user.get("telegram_id") or "скрыт"
        last_seen = format_compact_datetime(user.get("last_seen") or user.get("created_at"))
        blocks.append(
            f"{title}\n"
            f"ID: {telegram_id}\n"
            f"{messages_line}\n"
            f"Последняя активность: {last_seen}"
        )
    return "\n\n".join(blocks)


def render_top_users(title: str, users: list[dict], metric: str, suffix: str = "") -> str:
    if not users:
        return f"{title}\n• нет данных"

    lines = [title]
    for user in users:
        value = user.get(metric) or 0
        lines.append(f"• {user_display_name(user)} ({user_username(user)}, ID {user.get('telegram_id') or '—'}) — {value}{suffix}")
    return "\n".join(lines)

def render_banned_users(users: list[dict]) -> str:
    if not users:
        return "Заблокированных пользователей нет."

    blocks = []
    for user in users:
        username = f"@{user['username']}" if user.get("username") else "—"
        reason = user.get("reason") or "—"
        blocks.append(
            f"• Имя: {user.get('first_name') or '—'}\n"
            f"  Username: {username}\n"
            f"  Telegram ID: {user.get('telegram_id') or '—'}\n"
            f"  Дата блокировки: {format_db_datetime(user.get('banned_at'))}\n"
            f"  Причина: {reason}"
        )
    return "\n\n".join(blocks)


def render_help_text(user_id: int | None) -> str:
    help_text = (
        "Команды бота:\n\n"
        "/today — показать тренировку на сегодня\n"
        "/week — показать все тренировки на неделю\n"
        "/weight — твой вес\n"
        "/progress — показать историю веса и фото\n"
        "/help — показать этот список команд\n\n"
        "Фото без команды — автоматически сохранить как фото формы за текущую неделю.\n"
        "Кнопка ✅ Выполнено под тренировкой отмечает тренировку выполненной."
    )

    if user_id == settings.admin_user_id:
        help_text += (
            "\n\n"
            "Админ-команды:\n\n"
            "/stats\n"
            "/users\n"
            "/ban\n"
            "/unban\n"
            "/banned\n"
            "/broadcast\n"
            "/restart"
        )

    return help_text

class BannedUsersMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user or user.id == settings.admin_user_id:
            return await handler(event, data)

        banned = await db.is_banned(user.id, user.username)
        if not banned:
            return await handler(event, data)

        if isinstance(event, Message):
            sent = await event.answer("Доступ к боту ограничен.")
            await remember_outgoing(sent)
        elif isinstance(event, CallbackQuery):
            await event.answer("Доступ к боту ограничен.", show_alert=True)
            if event.message:
                sent = await event.message.answer("Доступ к боту ограничен.")
                await remember_outgoing(sent)
        return None


async def remember_incoming(message: Message) -> None:
    await db.record_user_activity(
        message.chat.id,
        message.from_user.id if message.from_user else None,
        message.from_user.username if message.from_user else None,
        message.from_user.first_name if message.from_user else None,
    )
    await db.save_message(message.chat.id, message.message_id, "in")


async def remember_outgoing(message: Message) -> Message:
    await db.save_message(message.chat.id, message.message_id, "out")
    return message


async def answer_and_remember(message: Message, text: str, **kwargs) -> Message:
    sent = await message.answer(text, **kwargs)
    await remember_outgoing(sent)
    return sent


async def send_daily_reminder(chat_id: int) -> None:
    target_date = today_local()
    training = get_training_for_date(program, target_date)
    sent = await bot.send_message(
        chat_id,
        render_training_message(training, target_date, progression_weeks(target_date)),
        reply_markup=daily_keyboard(),
    )
    await remember_outgoing(sent)


async def send_weekly_reminder(chat_id: int) -> None:
    sent = await bot.send_message(
        chat_id,
        "Еженедельный чек-ин.\n\n"
        "Введите актуальный вес через команду:\n"
        "/weight [ваш вес]\n\n"
        "Пример:\n"
        "/weight 82.5\n\n"
        "Потом отправь фото формы одним сообщением.",
        reply_markup=weekly_keyboard(),
    )
    await remember_outgoing(sent)
async def send_text_reminder(chat_id: int, text: str) -> None:
    sent = await bot.send_message(chat_id, text)
    await remember_outgoing(sent)


async def clear_known_chat_messages(chat_id: int, limit: int) -> int:
    message_ids = await db.list_message_ids(chat_id, limit)
    deleted_ids: list[int] = []

    for message_id in message_ids:
        try:
            await bot.delete_message(chat_id, message_id)
            deleted_ids.append(message_id)
        except Exception:
            continue

    await db.delete_message_records(chat_id, deleted_ids)
    return len(deleted_ids)


async def broadcast_daily() -> None:
    for chat_id in await db.list_chat_ids():
        try:
            await send_daily_reminder(chat_id)
        except Exception:
            logging.exception("Failed to send daily reminder to chat_id=%s", chat_id)


async def broadcast_weekly() -> None:
    for chat_id in await db.list_chat_ids():
        try:
            await send_weekly_reminder(chat_id)
        except Exception:
            logging.exception("Failed to send weekly reminder to chat_id=%s", chat_id)
async def broadcast_afternoon() -> None:
    for chat_id in await db.list_chat_ids():
        try:
            await send_text_reminder(
                chat_id,
                "Не забыл сегодня потренить? 👀\n\n"
                "Команды:\n"
                "/today — тренировка на сегодня\n"
                "/week — вся неделя"
            )
        except Exception:
            logging.exception("Failed to send second reminder to chat_id=%s", chat_id)


async def broadcast_sleep() -> None:
    for chat_id in await db.list_chat_ids():
        try:
            await send_text_reminder(chat_id, "Убираем телефончик и спать")
        except Exception:
            logging.exception("Failed to send sleep reminder to chat_id=%s", chat_id)



async def broadcast_clear() -> None:
    for chat_id in await db.list_chat_ids():
        try:
            await clear_known_chat_messages(chat_id, settings.clear_limit)
        except Exception:
            logging.exception("Failed to clear chat_id=%s", chat_id)


async def send_help_after_restart() -> None:
    chat_id = os.environ.pop("TRAINING_BOT_SHOW_HELP_CHAT_ID", None)
    if not chat_id:
        return

    try:
        sent = await bot.send_message(int(chat_id), render_help_text(settings.admin_user_id))
        await remember_outgoing(sent)
    except Exception:
        logging.exception("Failed to send help after restart to chat_id=%s", chat_id)


@dp.message(Command("start"))
async def start(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    await db.add_user(message.chat.id, message.from_user.first_name if message.from_user else None)

    await answer_and_remember(
        message,
        "Тренить будем?\n\n"
        "Используйте /help для списка доступных команд."
    )
    await log_request(message, "start", started_at)


@dp.message(Command("today"))
async def today(message: Message, remember_message: bool = True) -> None:
    started_at = perf_counter()
    if remember_message:
        await remember_incoming(message)
    await db.add_user(message.chat.id, message.from_user.first_name if message.from_user else None)
    await send_daily_reminder(message.chat.id)
    await log_request(message, "today", started_at)


@dp.message(Command("week"))
async def week(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    await db.add_user(message.chat.id, message.from_user.first_name if message.from_user else None)
    await answer_and_remember(message, render_week_message(program, progression_weeks(today_local())))
    await log_request(message, "week", started_at)


@dp.message(Command("help"))
async def help_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None
    await answer_and_remember(message, render_help_text(user_id))
    await log_request(message, "help", started_at)


@dp.message(Command("stats"))
async def stats(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None

    if user_id != settings.admin_user_id:
        await answer_and_remember(message, "Недостаточно прав.")
        await log_request(message, "stats_denied", started_at)
        return

    now = datetime.now(timezone)
    today_start = local_start_as_utc_naive(now.replace(hour=0, minute=0, second=0, microsecond=0))
    week_start_time = local_start_as_utc_naive((now - timedelta(days=now.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    ))
    stats_data = await db.get_admin_stats(today_start, week_start_time)
    user_stats = stats_data["user_stats"]

    await answer_and_remember(
        message,
        f"• Всего пользователей: {stats_data['users_total']}\n"
        f"• Всего сообщений: {stats_data['messages_total']}\n\n"
        "Пользователи:\n\n"
        f"• Всего пользователей: {user_stats['users_total']}\n"
        f"• Новых сегодня: {user_stats['new_today']}\n"
        f"• Новых за неделю: {user_stats['new_week']}\n"
        f"• Активных сегодня: {user_stats['active_today']}\n"
        f"• Активных за неделю: {user_stats['active_week']}\n\n"
        "Последние пользователи:\n\n"
        f"{render_user_details(stats_data['latest_users'])}\n\n"
        "ТОП пользователей:\n\n"
        f"{render_top_users('По количеству сообщений:', stats_data['top_messages'], 'messages_count')}"
    )
    await log_request(message, "stats", started_at)

@dp.message(Command("ban"))
async def ban_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None

    if user_id != settings.admin_user_id:
        await answer_and_remember(message, "Недостаточно прав.")
        await log_request(message, "ban_denied", started_at)
        return

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await answer_and_remember(message, "Использование: /ban <Telegram ID или @username> [причина]")
        await log_request(message, "ban", started_at, success=False, error="missing_target")
        return

    target = parts[1].strip()
    reason = parts[2].strip() if len(parts) > 2 else None
    found_user = await db.resolve_user(target)
    target_user_id = None
    if target.isdigit():
        target_user_id = int(target)
    elif found_user:
        target_user_id = found_user.get("telegram_id") or found_user.get("chat_id")

    if target_user_id == settings.admin_user_id:
        await answer_and_remember(message, "Недоступно.")
        await log_request(message, "ban", started_at, success=False, error="self_ban")
        return

    await db.ban_user(target, user_id, reason)
    await answer_and_remember(message, "Пользователь заблокирован.")
    await log_request(message, "ban", started_at)


@dp.message(Command("unban"))
async def unban_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None

    if user_id != settings.admin_user_id:
        await answer_and_remember(message, "Недостаточно прав.")
        await log_request(message, "unban_denied", started_at)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await answer_and_remember(message, "Использование: /unban <Telegram ID или @username>")
        await log_request(message, "unban", started_at, success=False, error="missing_target")
        return

    await db.unban_user(parts[1].strip())
    await answer_and_remember(message, "Пользователь разблокирован.")
    await log_request(message, "unban", started_at)


@dp.message(Command("banned"))
async def banned_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None

    if user_id != settings.admin_user_id:
        await answer_and_remember(message, "Недостаточно прав.")
        await log_request(message, "banned_denied", started_at)
        return

    banned_users = await db.list_banned_users()
    await answer_and_remember(message, f"Заблокированные пользователи:\n\n{render_banned_users(banned_users)}")
    await log_request(message, "banned", started_at)

async def restart_process() -> None:
    await asyncio.sleep(1)
    await bot.session.close()
    os.execv(sys.executable, [sys.executable, *sys.argv])


@dp.message(Command("restart"))
async def restart_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None

    if user_id != settings.admin_user_id:
        await answer_and_remember(message, "Недостаточно прав.")
        await log_request(message, "restart_denied", started_at)
        return

    await answer_and_remember(message, "Перезапускаю бота.")
    await log_request(message, "restart", started_at)
    os.environ["TRAINING_BOT_SHOW_HELP_CHAT_ID"] = str(message.chat.id)
    asyncio.create_task(restart_process())

@dp.message(Command("broadcast"))
async def broadcast_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None

    if user_id != settings.admin_user_id:
        await answer_and_remember(message, "Команда недоступна.")
        await log_request(message, "broadcast_denied", started_at)
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await answer_and_remember(
            message,
            "Введите сообщение для рассылки.\n\n"
            "Пример:\n"
            "/broadcast Завтра выходной"
        )
        await log_request(message, "broadcast", started_at, success=False, error="missing_text")
        return

    announcement = f"📢 Объявление\n\n{parts[1].strip()}"
    success_count = 0
    error_count = 0

    for chat_id in await db.list_chat_ids():
        try:
            sent = await bot.send_message(chat_id, announcement)
            await remember_outgoing(sent)
            success_count += 1
        except Exception:
            error_count += 1
            logging.exception("Failed to broadcast message to chat_id=%s", chat_id)

    await answer_and_remember(
        message,
        "Рассылка завершена.\n\n"
        f"Успешно: {success_count}\n"
        f"Ошибок: {error_count}"
    )
    await log_request(message, "broadcast", started_at)


@dp.message(Command("users"))
async def users_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    user_id = message.from_user.id if message.from_user else None

    if user_id != settings.admin_user_id:
        await answer_and_remember(message, "Недостаточно прав.")
        await log_request(message, "users_denied", started_at)
        return

    page_size = 10
    parts = (message.text or "").split(maxsplit=1)
    argument = parts[1].strip() if len(parts) > 1 else None
    page = 1
    query = argument
    if argument and argument.isdigit() and len(argument) <= 3:
        page = max(1, int(argument))
        query = None

    total_users = await db.count_users(query)
    offset = (page - 1) * page_size
    users = await db.search_users(query, page_size, offset)
    shown_to = min(offset + len(users), total_users)
    title = "Пользователи" if not query else f"Пользователи по запросу: {query}"
    await answer_and_remember(
        message,
        f"{title}\n"
        f"Показано {shown_to} из {total_users} пользователей.\n\n"
        f"{render_compact_users(users, offset + 1)}"
    )
    await log_request(message, "users", started_at)


@dp.message(Command("clear"))
async def clear_chat(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    deleted = await clear_known_chat_messages(message.chat.id, settings.clear_limit)
    await answer_and_remember(
        message,
        "История почищена. Продолжаем тренироваться зайчик."
    )
    await log_request(message, "clear", started_at)


@dp.message(Command("weight"))
async def weight_command(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    parts = (message.text or "").replace(",", ".").split()
    if len(parts) < 2:
        rows = await db.get_recent_weight_logs(message.chat.id, 2)
        current = rows[0] if rows else None
        previous = rows[1] if len(rows) > 1 else None

        current_text = f"{current['weight_kg']:g} кг" if current else "не указан"
        previous_text = f"{previous['weight_kg']:g} кг" if previous else "нет данных"

        if current and previous:
            diff = float(current["weight_kg"]) - float(previous["weight_kg"])
            change_text = f"{diff:+.1f} кг"
        else:
            change_text = "нет данных"

        await answer_and_remember(
            message,
            "Текущий вес: "
            f"{current_text}\n"
            "Вес за прошлую запись: "
            f"{previous_text}\n"
            "Изменение: "
            f"{change_text}\n\n"
            "Введите актуальный вес через команду:\n\n"
            "/weight [ваш вес]\n\n"
            "Записать новый вес"
        )
        await log_request(message, "weight", started_at)
        return

    try:
        weight = float(parts[1])
    except ValueError:
        await answer_and_remember(
            message,
            "Не смог распознать вес.\n\n"
            "Введите актуальный вес через команду:\n\n"
            "/weight [ваш вес]\n\n"
            "Пример:\n\n"
            "/weight 82.5"
        )
        await log_request(message, "weight", started_at, success=False, error="invalid_weight")
        return

    target_date = today_local()
    await db.save_weight(message.chat.id, week_start(target_date), weight, target_date)
    await answer_and_remember(message, f"Записал вес за текущую неделю: {weight:g} кг")
    await log_request(message, "weight", started_at)


@dp.message(Command("progress"))
async def progress(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    rows = await db.get_weekly_logs(message.chat.id)
    if not rows:
        await answer_and_remember(message, "Пока нет записей прогресса. Запиши вес через /weight и отправь фото.")
        await log_request(message, "progress", started_at)
        return

    lines = ["Прогресс:"]
    photo_rows = []
    for row in rows:
        weight = f"{row['weight_kg']:g} кг" if row["weight_kg"] is not None else "не записан"
        weight_date = row["weight_date"] or "—"
        photo_status = f"есть, дата {row['photo_date']}" if row["photo_file_id"] else "нет"
        lines.append(
            f"\nНеделя с {row['week_start']}\n"
            f"Вес: {weight} — дата {weight_date}\n"
            f"Фото: {photo_status}"
        )
        if row["photo_file_id"]:
            photo_rows.append(row)

    await answer_and_remember(message, "\n".join(lines))

    for row in photo_rows[:10]:
        sent_photo = await bot.send_photo(
            message.chat.id,
            row["photo_file_id"],
            caption=f"Фото формы: неделя с {row['week_start']}, дата {row['photo_date'] or '—'}",
        )
        await remember_outgoing(sent_photo)
    await log_request(message, "progress", started_at)


@dp.message(F.photo)
async def photo(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    await db.add_user(message.chat.id, message.from_user.first_name if message.from_user else None)
    photo_file_id = message.photo[-1].file_id
    target_date = today_local()
    await db.save_photo(message.chat.id, week_start(target_date), photo_file_id, target_date)
    await answer_and_remember(message, "Сохранил фото формы за текущую неделю.")
    await log_request(message, "photo", started_at)


@dp.message(F.text.regexp(r"^\d+([,.]\d+)?$"))
async def plain_weight(message: Message) -> None:
    started_at = perf_counter()
    await remember_incoming(message)
    weight = float((message.text or "").replace(",", "."))
    target_date = today_local()
    await db.save_weight(message.chat.id, week_start(target_date), weight, target_date)
    await answer_and_remember(message, f"Записал вес за текущую неделю: {weight:g} кг")
    await log_request(message, "plain_weight", started_at)


@dp.callback_query(F.data == "daily:done")
async def daily_done(callback: CallbackQuery) -> None:
    await db.save_daily_status(callback.message.chat.id, today_local(), "done")
    await callback.answer("Отмечено выполненным")
    sent = await callback.message.answer("Тренировка отмечена как выполненная.")
    await remember_outgoing(sent)


@dp.callback_query(F.data == "daily:skip")
async def daily_skip(callback: CallbackQuery) -> None:
    await db.save_daily_status(callback.message.chat.id, today_local(), "skipped")
    await callback.answer("Отмечено как пропуск")
    sent = await callback.message.answer("Пропуск записан. Завтра продолжаем по плану.")
    await remember_outgoing(sent)


@dp.callback_query(F.data == "weekly:weight_help")
async def weekly_weight_help(callback: CallbackQuery) -> None:
    await callback.answer()
    sent = await callback.message.answer(
        "Введите актуальный вес через команду:\n\n"
        "/weight [ваш вес]\n\n"
        "Пример:\n\n"
        "/weight 82.5"
    )
    await remember_outgoing(sent)


@dp.callback_query(F.data == "weekly:photo_help")
async def weekly_photo_help(callback: CallbackQuery) -> None:
    await callback.answer()
    sent = await callback.message.answer("Отправь фото формы прямо сюда. Я сохраню Telegram file_id за текущую неделю.")
    await remember_outgoing(sent)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    await db.init()
    dp.message.middleware(BannedUsersMiddleware())
    dp.callback_query.middleware(BannedUsersMiddleware())
    await bot.set_my_commands(
        [
            BotCommand(command="help", description="Список команд"),
        ]
    )

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    daily_hour, daily_minute = parse_time(settings.daily_reminder_time)
    weekly_hour, weekly_minute = parse_time(settings.weekly_reminder_time)
    afternoon_hour, afternoon_minute = parse_time(settings.afternoon_reminder_time)
    sleep_hour, sleep_minute = parse_time(settings.sleep_reminder_time)
    clear_hour, clear_minute = parse_time(settings.clear_time)

    scheduler.add_job(
        broadcast_daily,
        CronTrigger(hour=daily_hour, minute=daily_minute, timezone=settings.timezone),
        id="daily_reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        broadcast_weekly,
        CronTrigger(
            day_of_week=WEEKDAYS.get(settings.weekly_reminder_day, "sun"),
            hour=weekly_hour,
            minute=weekly_minute,
            timezone=settings.timezone,
        ),
        id="weekly_reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        broadcast_afternoon,
        CronTrigger(hour=afternoon_hour, minute=afternoon_minute, timezone=settings.timezone),
        id="second_reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        broadcast_sleep,
        CronTrigger(hour=sleep_hour, minute=sleep_minute, timezone=settings.timezone),
        id="sleep_reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        broadcast_clear,
        CronTrigger(hour=clear_hour, minute=clear_minute, timezone=settings.timezone),
        id="daily_clear",
        replace_existing=True,
    )
    scheduler.start()
    logging.info("Scheduled daily reminder 10:00: %s", settings.daily_reminder_time)
    logging.info("Scheduled second reminder 15:00: %s", settings.afternoon_reminder_time)
    logging.info(
        "Scheduled weekly check-in: %s %s",
        settings.weekly_reminder_day,
        settings.weekly_reminder_time,
    )
    await send_help_after_restart()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
