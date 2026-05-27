from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_user_id: int | None
    timezone: str
    daily_reminder_time: str
    weekly_reminder_day: str
    weekly_reminder_time: str
    afternoon_reminder_time: str
    sleep_reminder_time: str
    clear_time: str
    clear_limit: int
    program_start_date: str
    database_path: Path
    program_path: Path


def _path_from_env(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return BASE_DIR / path


def load_settings() -> Settings:
    load_dotenv(BASE_DIR / ".env")

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is required. Copy .env.example to .env and set your BotFather token.")

    return Settings(
        bot_token=token,
        admin_user_id=int(os.getenv("ADMIN_USER_ID", "0") or "0") or None,
        timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip(),
        daily_reminder_time=os.getenv("DAILY_REMINDER_TIME", "09:00").strip(),
        weekly_reminder_day=os.getenv("WEEKLY_REMINDER_DAY", "sunday").strip().lower(),
        weekly_reminder_time=os.getenv("WEEKLY_REMINDER_TIME", "10:00").strip(),
        afternoon_reminder_time=os.getenv("AFTERNOON_REMINDER_TIME", "15:00").strip(),
        sleep_reminder_time=os.getenv("SLEEP_REMINDER_TIME", "23:59").strip(),
        clear_time=os.getenv("CLEAR_TIME", "21:00").strip(),
        clear_limit=int(os.getenv("CLEAR_LIMIT", "1000")),
        program_start_date=os.getenv("PROGRAM_START_DATE", "2026-05-27").strip(),
        database_path=_path_from_env(os.getenv("DATABASE_PATH", "data/bot.sqlite3")),
        program_path=_path_from_env(os.getenv("PROGRAM_PATH", "data/program.json")),
    )
