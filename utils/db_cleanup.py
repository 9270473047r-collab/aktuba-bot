import os
import aiosqlite


DB_PATH = os.getenv("DATABASE_PATH", "data/aktuba.db")


async def cleanup_keep_users():
    """
    Очищает все таблицы в SQLite БД, кроме таблицы users.
    Схему НЕ трогает, только данные.
    """
    conn = await aiosqlite.connect(DB_PATH, timeout=30)
    try:
        conn.row_factory = aiosqlite.Row

        # чтобы не упереться в FK при массовой очистке
        await conn.execute("PRAGMA foreign_keys = OFF;")

        cur = await conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
        """)
        rows = await cur.fetchall()
        await cur.close()

        tables = [r["name"] for r in rows if r and r["name"]]

        for t in tables:
            if t == "users":
                continue
            await conn.execute(f"DELETE FROM {t};")

        # сброс автоинкрементов (если таблица sqlite_sequence существует)
        try:
            await conn.execute("DELETE FROM sqlite_sequence WHERE name != 'users';")
        except Exception:
            pass

        await conn.commit()

        # включим обратно
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.commit()

    finally:
        await conn.close()
