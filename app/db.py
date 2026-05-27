from datetime import date, datetime
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    telegram_id INTEGER,
                    username TEXT,
                    first_name TEXT,
                    created_at TEXT NOT NULL,
                    first_seen TEXT,
                    last_seen TEXT,
                    messages_count INTEGER NOT NULL DEFAULT 0,
                    requests_count INTEGER NOT NULL DEFAULT 0,
                    tokens_used INTEGER NOT NULL DEFAULT 0,
                    total_cost REAL NOT NULL DEFAULT 0
                );


                CREATE TABLE IF NOT EXISTS daily_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    log_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(chat_id, log_date)
                );

                CREATE TABLE IF NOT EXISTS weekly_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    week_start TEXT NOT NULL,
                    weight_kg REAL,
                    weight_date TEXT,
                    photo_file_id TEXT,
                    photo_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(chat_id, week_start)
                );

                CREATE TABLE IF NOT EXISTS chat_messages (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    direction TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(chat_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS bot_request_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_id INTEGER,
                    chat_id INTEGER NOT NULL,
                    command_type TEXT NOT NULL,
                    is_ai_request INTEGER NOT NULL DEFAULT 0,
                    duration_seconds REAL NOT NULL DEFAULT 0,
                    success INTEGER NOT NULL DEFAULT 1,
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_bot_request_logs_timestamp
                ON bot_request_logs(timestamp);
                """
            )
            await self._ensure_column(db, "users", "telegram_id", "INTEGER")
            await self._ensure_column(db, "users", "username", "TEXT")
            await self._ensure_column(db, "users", "first_seen", "TEXT")
            await self._ensure_column(db, "users", "last_seen", "TEXT")
            await self._ensure_column(db, "users", "messages_count", "INTEGER NOT NULL DEFAULT 0")
            await self._ensure_column(db, "users", "requests_count", "INTEGER NOT NULL DEFAULT 0")
            await self._ensure_column(db, "users", "tokens_used", "INTEGER NOT NULL DEFAULT 0")
            await self._ensure_column(db, "users", "total_cost", "REAL NOT NULL DEFAULT 0")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            await self._ensure_column(db, "weekly_logs", "weight_date", "TEXT")
            await self._ensure_column(db, "weekly_logs", "photo_date", "TEXT")
            await self._ensure_column(db, "bot_request_logs", "is_ai_request", "INTEGER NOT NULL DEFAULT 0")
            await db.execute("UPDATE users SET first_seen = COALESCE(first_seen, created_at)")
            await db.execute("UPDATE users SET last_seen = COALESCE(last_seen, created_at)")
            await db.commit()

    async def _ensure_column(self, db: aiosqlite.Connection, table: str, column: str, column_type: str) -> None:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in await cursor.fetchall()}
        if column not in columns:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    async def add_user(self, chat_id: int, first_name: str | None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users(chat_id, first_name, created_at, first_seen, last_seen)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    first_name = COALESCE(excluded.first_name, users.first_name)
                """,
                (
                    chat_id,
                    first_name,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            await db.commit()

    async def get_user(self, chat_id: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE chat_id = ?",
                (chat_id,),
            )
            row = await cursor.fetchone()
        return dict(row) if row else None

    async def record_user_activity(
        self,
        chat_id: int,
        telegram_id: int | None,
        username: str | None,
        first_name: str | None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users(
                    chat_id, telegram_id, username, first_name, created_at, first_seen,
                    last_seen, messages_count, requests_count, tokens_used, total_cost
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, 1, 0, 0, 0)
                ON CONFLICT(chat_id) DO UPDATE SET
                    telegram_id = COALESCE(excluded.telegram_id, users.telegram_id),
                    username = COALESCE(excluded.username, users.username),
                    first_name = COALESCE(excluded.first_name, users.first_name),
                    first_seen = COALESCE(users.first_seen, users.created_at, excluded.first_seen),
                    last_seen = excluded.last_seen,
                    messages_count = users.messages_count + 1
                """,
                (chat_id, telegram_id, username, first_name, now, now, now),
            )
            await db.commit()

    async def save_request_log(
        self,
        chat_id: int,
        user_id: int | None,
        command_type: str,
        is_ai_request: bool = False,
        duration_seconds: float = 0,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO bot_request_logs(
                    timestamp, user_id, chat_id, command_type, is_ai_request,
                    duration_seconds, success, error
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    user_id,
                    chat_id,
                    command_type,
                    1 if is_ai_request else 0,
                    duration_seconds,
                    1 if success else 0,
                    error,
                ),
            )
            if is_ai_request and user_id is not None:
                await db.execute(
                    """
                    UPDATE users
                    SET requests_count = requests_count + 1
                    WHERE telegram_id = ?
                    """,
                    (user_id,),
                )
            await db.commit()

    async def get_admin_stats(self, today_start: datetime, week_start: datetime) -> dict[str, Any]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row

            users_cursor = await db.execute("SELECT COUNT(*) AS total FROM users")
            users_total = (await users_cursor.fetchone())["total"]

            messages_cursor = await db.execute("SELECT COUNT(*) AS total FROM chat_messages")
            messages_total = (await messages_cursor.fetchone())["total"]

            totals_cursor = await db.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN is_ai_request = 1 THEN 1 ELSE 0 END), 0) AS total_ai_requests,
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND is_ai_request = 1 THEN 1 ELSE 0 END), 0) AS requests_today,
                    COALESCE(SUM(CASE WHEN timestamp >= ? AND is_ai_request = 1 THEN 1 ELSE 0 END), 0) AS requests_week
                FROM bot_request_logs
                """,
                (
                    today_start.isoformat(),
                    week_start.isoformat(),
                ),
            )
            totals = dict(await totals_cursor.fetchone())
            user_stats_cursor = await db.execute(
                """
                SELECT
                    COUNT(*) AS users_total,
                    COALESCE(SUM(CASE WHEN first_seen >= ? THEN 1 ELSE 0 END), 0) AS new_today,
                    COALESCE(SUM(CASE WHEN first_seen >= ? THEN 1 ELSE 0 END), 0) AS new_week,
                    COALESCE(SUM(CASE WHEN last_seen >= ? THEN 1 ELSE 0 END), 0) AS active_today,
                    COALESCE(SUM(CASE WHEN last_seen >= ? THEN 1 ELSE 0 END), 0) AS active_week
                FROM users
                """,
                (
                    today_start.isoformat(),
                    week_start.isoformat(),
                    today_start.isoformat(),
                    week_start.isoformat(),
                ),
            )
            user_stats = dict(await user_stats_cursor.fetchone())

            latest_users = await self._fetch_users(
                db,
                """
                SELECT *
                FROM users
                ORDER BY COALESCE(first_seen, created_at) DESC
                LIMIT 5
                """,
            )
            top_messages = await self._fetch_users(
                db,
                """
                SELECT *
                FROM users
                ORDER BY messages_count DESC, COALESCE(last_seen, created_at) DESC
                LIMIT 5
                """,
            )
            top_ai = await self._fetch_users(
                db,
                """
                SELECT *
                FROM users
                ORDER BY requests_count DESC, COALESCE(last_seen, created_at) DESC
                LIMIT 5
                """,
            )
            top_tokens = await self._fetch_users(
                db,
                """
                SELECT *
                FROM users
                ORDER BY tokens_used DESC, COALESCE(last_seen, created_at) DESC
                LIMIT 5
                """,
            )

        return {
            "users_total": users_total,
            "messages_total": messages_total,
            "user_stats": user_stats,
            "latest_users": latest_users,
            "top_messages": top_messages,
            "top_ai": top_ai,
            "top_tokens": top_tokens,
            **totals,
        }

    async def _fetch_users(
        self,
        db: aiosqlite.Connection,
        query: str,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        cursor = await db.execute(query, parameters)
        return [dict(row) for row in await cursor.fetchall()]

    async def search_users(self, query: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            if query:
                normalized = query.strip()
                username = normalized[1:] if normalized.startswith("@") else normalized
                if normalized.isdigit():
                    return await self._fetch_users(
                        db,
                        """
                        SELECT *
                        FROM users
                        WHERE telegram_id = ? OR chat_id = ?
                        ORDER BY COALESCE(last_seen, created_at) DESC
                        LIMIT ?
                        """,
                        (int(normalized), int(normalized), limit),
                    )

                pattern = f"%{username}%"
                return await self._fetch_users(
                    db,
                    """
                    SELECT *
                    FROM users
                    WHERE LOWER(COALESCE(first_name, '')) LIKE LOWER(?)
                       OR LOWER(COALESCE(username, '')) LIKE LOWER(?)
                    ORDER BY COALESCE(last_seen, created_at) DESC
                    LIMIT ?
                    """,
                    (pattern, pattern, limit),
                )

            return await self._fetch_users(
                db,
                """
                SELECT *
                FROM users
                ORDER BY COALESCE(last_seen, created_at) DESC
                LIMIT ?
                """,
                (limit,),
            )

    async def list_chat_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute("SELECT chat_id FROM users")
            rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def save_daily_status(self, chat_id: int, log_date: date, status: str, note: str | None = None) -> None:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO daily_logs(chat_id, log_date, status, note, created_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, log_date) DO UPDATE SET
                    status = excluded.status,
                    note = COALESCE(excluded.note, daily_logs.note)
                """,
                (chat_id, log_date.isoformat(), status, note, now),
            )
            await db.commit()

    async def save_weight(self, chat_id: int, week_start: date, weight_kg: float, weight_date: date) -> None:
        await self._upsert_weekly(
            chat_id,
            week_start,
            {"weight_kg": weight_kg, "weight_date": weight_date.isoformat()},
        )

    async def save_photo(self, chat_id: int, week_start: date, photo_file_id: str, photo_date: date) -> None:
        await self._upsert_weekly(
            chat_id,
            week_start,
            {"photo_file_id": photo_file_id, "photo_date": photo_date.isoformat()},
        )

    async def _upsert_weekly(self, chat_id: int, week_start: date, values: dict[str, Any]) -> None:
        now = datetime.utcnow().isoformat()
        weight = values.get("weight_kg")
        weight_date = values.get("weight_date")
        photo = values.get("photo_file_id")
        photo_date = values.get("photo_date")

        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO weekly_logs(chat_id, week_start, weight_kg, weight_date, photo_file_id, photo_date, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, week_start) DO UPDATE SET
                    weight_kg = COALESCE(excluded.weight_kg, weekly_logs.weight_kg),
                    weight_date = COALESCE(excluded.weight_date, weekly_logs.weight_date),
                    photo_file_id = COALESCE(excluded.photo_file_id, weekly_logs.photo_file_id),
                    photo_date = COALESCE(excluded.photo_date, weekly_logs.photo_date),
                    updated_at = excluded.updated_at
                """,
                (chat_id, week_start.isoformat(), weight, weight_date, photo, photo_date, now, now),
            )
            await db.commit()

    async def get_weekly_logs(self, chat_id: int) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT week_start, weight_kg, weight_date, photo_file_id, photo_date, updated_at
                FROM weekly_logs
                WHERE chat_id = ?
                ORDER BY week_start DESC
                """,
                (chat_id,),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_recent_weight_logs(self, chat_id: int, limit: int = 2) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT week_start, weight_kg, weight_date, updated_at
                FROM weekly_logs
                WHERE chat_id = ? AND weight_kg IS NOT NULL
                ORDER BY COALESCE(weight_date, week_start) DESC, updated_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def save_message(self, chat_id: int, message_id: int, direction: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT OR IGNORE INTO chat_messages(chat_id, message_id, direction, created_at)
                VALUES(?, ?, ?, ?)
                """,
                (chat_id, message_id, direction, datetime.utcnow().isoformat()),
            )
            await db.commit()

    async def list_message_ids(self, chat_id: int, limit: int) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            cursor = await db.execute(
                """
                SELECT message_id
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY message_id DESC
                LIMIT ?
                """,
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def delete_message_records(self, chat_id: int, message_ids: list[int]) -> None:
        if not message_ids:
            return

        async with aiosqlite.connect(self.path) as db:
            await db.executemany(
                "DELETE FROM chat_messages WHERE chat_id = ? AND message_id = ?",
                [(chat_id, message_id) for message_id in message_ids],
            )
            await db.commit()