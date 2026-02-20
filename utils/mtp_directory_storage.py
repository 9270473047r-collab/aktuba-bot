from __future__ import annotations

import os
from typing import List, Dict, Optional
from datetime import datetime

import aiosqlite


def _resolve_db_path() -> str:
    # 1) ENV
    env_path = os.getenv("DB_PATH")
    if env_path:
        return env_path

    # 2) config.py (если есть DB_PATH)
    try:
        import config  # type: ignore
        if hasattr(config, "DB_PATH"):
            return str(getattr(config, "DB_PATH"))
    except Exception:
        pass

    # 3) db.py (если есть DB_PATH рядом)
    try:
        import db  # type: ignore
        if hasattr(db, "DB_PATH"):
            return str(getattr(db, "DB_PATH"))
    except Exception:
        pass

    # 4) fallback: файл рядом с проектом
    base_dir = os.path.dirname(os.path.dirname(__file__))  # aktuba_bot/
    return os.path.join(base_dir, "bot.db")


class MtpDirectoryStorage:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _resolve_db_path()

    async def ensure_schema(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS mtp_directory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    unit_name      TEXT NOT NULL,
                    equipment_name TEXT NOT NULL,
                    inv_number     TEXT NOT NULL,
                    year           TEXT,
                    responsible    TEXT NOT NULL,
                    comment        TEXT,
                    created_by     INTEGER,
                    created_at     TEXT DEFAULT (datetime('now'))
                );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mtp_directory_inv_number ON mtp_directory(inv_number);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_mtp_directory_unit_name ON mtp_directory(unit_name);")
            await db.commit()

    async def add_item(
        self,
        unit_name: str,
        equipment_name: str,
        inv_number: str,
        year: Optional[str],
        responsible: str,
        comment: Optional[str],
        created_by: int,
    ) -> None:
        await self.ensure_schema()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO mtp_directory (unit_name, equipment_name, inv_number, year, responsible, comment, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (unit_name, equipment_name, inv_number, year, responsible, comment, created_by),
            )
            await db.commit()

    async def list_items(self, limit: int = 200) -> List[Dict]:
        await self.ensure_schema()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT id, unit_name, equipment_name, inv_number, year, responsible, comment, created_by, created_at
                  FROM mtp_directory
                 ORDER BY id DESC
                 LIMIT ?
                """,
                (limit,),
            )
            rows = await cur.fetchall()
            await cur.close()
        return [dict(r) for r in rows]
