# db.py  — единый модуль работы с БД
# ----------------------------------
from __future__ import annotations

import os, logging, sqlite3, aiosqlite, traceback
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")

MILK_PRICE_DEFAULTS: Dict[str, Dict[str, float]] = {
    "aktuba": {
        "kantal": 41.0,
        "chmk": 41.0,
        "siyfat": 40.0,
        "tnurs": 40.0,
        "zai": 26.0,
        "cafeteria": 40.0,
        "salary": 40.0,
    },
    "karamaly": {
        "kantal": 41.0,
        "chmk": 41.0,
        "siyfat": 40.0,
        "tnurs": 40.0,
        "zai": 26.0,
        "cafeteria": 40.0,
        "salary": 40.0,
    },
    "sheremetyovo": {
        "kantal": 41.0,
        "chmk": 41.0,
        "siyfat": 40.0,
        "tnurs": 40.0,
        "zai": 26.0,
        "cafeteria": 40.0,
        "salary": 40.0,
    },
}


class Database:
    def __init__(self) -> None:
        self.conn: aiosqlite.Connection | None = None

    # ---------- подключение и миграции ----------
    async def connect(self):
        self.conn = await aiosqlite.connect(DB_PATH)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys = ON")
        logger.info("✅ Соединение с БД открыто")

        await self._create_schema()
        await self._apply_migrations()
        await self._seed_milk_prices_defaults()
        await self.conn.commit()
        logger.info("✅ Схема актуальна")

    # ---------- начальное создание таблиц ----------
    async def _create_schema(self):
        # USERS -----------------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER UNIQUE NOT NULL,
                full_name    TEXT NOT NULL,
                phone        TEXT UNIQUE,
                department   TEXT,
                block        TEXT,
                role         TEXT,                     -- должность
                position     TEXT DEFAULT 'сотрудник', -- уровень доступа
                is_confirmed INTEGER DEFAULT 0,
                is_admin     INTEGER DEFAULT 0,
                is_active    INTEGER DEFAULT 1,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP,
                last_active  TIMESTAMP
            );
        """)

        # TASKS -----------------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                global_num   TEXT,
                user_num     INTEGER,
                title        TEXT NOT NULL,
                description  TEXT,
                assigned_by  INTEGER NOT NULL REFERENCES users(user_id),
                assigned_to  INTEGER NOT NULL REFERENCES users(user_id),
                deadline     DATE NOT NULL,
                status       TEXT DEFAULT 'pending'
                              CHECK(status IN ('pending','in_progress','wait_confirm','completed','overdue','canceled')),
                priority     INTEGER DEFAULT 1 CHECK(priority BETWEEN 1 AND 5),
                is_accepted  INTEGER DEFAULT 0,
                file_id      TEXT,
                file_type    TEXT,
                confirm_status TEXT DEFAULT 'wait'
                               CHECK(confirm_status IN ('wait','confirmed','rejected')),
                fine_amount  INTEGER DEFAULT 0,
                fine_comment TEXT,
                fine_confirmed INTEGER DEFAULT 0,
                reject_comment TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at   TIMESTAMP,
                completed_at TIMESTAMP
            );
        """)

        # REPORTS ---------------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL REFERENCES users(user_id),
                date     DATE NOT NULL DEFAULT CURRENT_DATE,
                text     TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # MILK REPORTS ---------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS milk_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location    TEXT NOT NULL,         -- aktuba / karamaly / sheremetyovo / soyuz_agro
                report_date DATE NOT NULL,
                data_json   TEXT NOT NULL,         -- JSON с цифрами
                created_by  INTEGER REFERENCES users(user_id),
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP,
                UNIQUE(location, report_date)
            );
        """)
# VET REPORTS ---------------------------------------------------
        await self.conn.execute("""
    CREATE TABLE IF NOT EXISTS vet_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        location    TEXT NOT NULL,
        report_type TEXT NOT NULL,
        report_date DATE NOT NULL,
        data_json   TEXT NOT NULL,
        created_by  INTEGER REFERENCES users(user_id),
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP,
        UNIQUE(location, report_type, report_date)
    );
""")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_vet_reports_ltrd ON vet_reports(location, report_type, report_date);")
        # KPI -------------------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS kpi (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(user_id),
                period  TEXT CHECK(period IN ('daily','weekly','monthly')),
                value   REAL NOT NULL,
                target  REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # DEPARTMENTS -----------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                parent_id  INTEGER REFERENCES departments(id),
                manager_id INTEGER REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # ADMIN LOGS ------------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL REFERENCES users(user_id),
                action_type TEXT NOT NULL,
                target_id   INTEGER,
                details     TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # DOCUMENTS -------------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                category  TEXT,
                department_id INTEGER REFERENCES departments(id),
                created_by INTEGER NOT NULL REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # FINES -----------------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS fines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(user_id),
                amount  INTEGER NOT NULL CHECK(amount>0),
                reason  TEXT NOT NULL,
                task_id INTEGER REFERENCES tasks(id),
                status  TEXT DEFAULT 'pending'
                         CHECK(status IN ('pending','confirmed','canceled')),
                created_by INTEGER NOT NULL REFERENCES users(user_id),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            );
        """)

        # MTP DIRECTORY ---------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS mtp_directory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_name      TEXT NOT NULL,  -- подразделение/отделение
                equipment_name TEXT NOT NULL,  -- наименование техники
                inv_number     TEXT NOT NULL,  -- инв/гос номер
                year           TEXT,           -- год выпуска (может быть null)
                responsible    TEXT NOT NULL,  -- ответственный
                comment        TEXT,           -- комментарий
                created_by     INTEGER REFERENCES users(user_id),
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_mtp_directory_inv_number ON mtp_directory(inv_number);")
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_mtp_directory_unit_name  ON mtp_directory(unit_name);")

        # MILK PRICES -----------------------------------------------------
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS milk_prices (
                location    TEXT NOT NULL,
                counterparty TEXT NOT NULL,
                price       REAL NOT NULL,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(location, counterparty)
            );
        """)
        await self.conn.execute("""
            CREATE TABLE IF NOT EXISTS milk_price_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                location     TEXT NOT NULL,
                counterparty TEXT NOT NULL,
                old_price    REAL,
                new_price    REAL NOT NULL,
                changed_by   INTEGER REFERENCES users(user_id),
                changed_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self.conn.execute("CREATE INDEX IF NOT EXISTS idx_milk_price_logs_changed_at ON milk_price_logs(changed_at DESC);")

    # ---------- миграции к старым БД ----------
    async def _apply_migrations(self):
        migrations = [
            # users.updated_at (нужен для ON CONFLICT)
            "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP;",
            # users.position (если базы совсем старая)
            "ALTER TABLE users ADD COLUMN position TEXT DEFAULT 'сотрудник';",
            # users.block (для разделения department/block)
            "ALTER TABLE users ADD COLUMN block TEXT;",
            # tasks.priority (для индекса priority)
            "ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 1 CHECK(priority BETWEEN 1 AND 5);",
            # tasks.global_num / user_num (нумерация задач)
            "ALTER TABLE tasks ADD COLUMN global_num TEXT;",
            "ALTER TABLE tasks ADD COLUMN user_num INTEGER;",
            # индексы
						"CREATE TABLE IF NOT EXISTS vet_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, location TEXT NOT NULL, report_type TEXT NOT NULL, report_date DATE NOT NULL, data_json TEXT NOT NULL, created_by INTEGER REFERENCES users(user_id), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP, UNIQUE(location, report_type, report_date));",
            "CREATE INDEX IF NOT EXISTS idx_vet_reports_ltrd ON vet_reports(location, report_type, report_date);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);",
            "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);",
            "CREATE INDEX IF NOT EXISTS idx_fines_status   ON fines(status);",
            "CREATE TABLE IF NOT EXISTS milk_prices (location TEXT NOT NULL, counterparty TEXT NOT NULL, price REAL NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(location, counterparty));",
            "CREATE TABLE IF NOT EXISTS milk_price_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, location TEXT NOT NULL, counterparty TEXT NOT NULL, old_price REAL, new_price REAL NOT NULL, changed_by INTEGER REFERENCES users(user_id), changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);",
            "CREATE INDEX IF NOT EXISTS idx_milk_price_logs_changed_at ON milk_price_logs(changed_at DESC);",
        ]
        for sql in migrations:
            try:
                await self.conn.execute(sql)
            except sqlite3.OperationalError as e:
                # пропускаем «duplicate column» и «already exists»
                if "duplicate" not in str(e).lower() and "exists" not in str(e).lower():
                    logger.warning("⚠️ Миграция не применена:\n%s\n%s", sql, e)

    async def _seed_milk_prices_defaults(self) -> None:
        for location, items in MILK_PRICE_DEFAULTS.items():
            for counterparty, price in items.items():
                await self.conn.execute(
                    """
                    INSERT OR IGNORE INTO milk_prices (location, counterparty, price, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (location, counterparty, float(price)),
                )

    # ---------- USER QUERIES ----------
    async def get_user(self, user_id: int) -> Optional[Dict]:
        cur = await self.conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    async def get_user_by_phone(self, phone: str) -> Optional[Dict]:
        cur = await self.conn.execute("SELECT * FROM users WHERE phone=?", (phone,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    async def get_user_by_name(self, full_name: str) -> Optional[Dict]:
        cur = await self.conn.execute("SELECT * FROM users WHERE full_name=?", (full_name,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    async def delete_user(self, user_id: int) -> bool:
        """Удалить пользователя (например, при отклонении заявки)."""
        try:
            await self.conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
            await self.conn.commit()
            return True
        except Exception:
            logger.error("❌ Ошибка удаления пользователя:\n%s", traceback.format_exc())
            return False

    async def update_role_by_full_name(self, full_name: str, new_role: str) -> bool:
        """Обновить роль пользователя по ФИО. Возвращает True, если обновлена хотя бы одна строка."""
        try:
            cur = await self.conn.execute(
                "UPDATE users SET role = ?, updated_at = CURRENT_TIMESTAMP WHERE full_name = ?",
                (new_role.strip(), full_name.strip()),
            )
            await self.conn.commit()
            return cur.rowcount > 0
        except Exception:
            logger.error("❌ Ошибка обновления роли:\n%s", traceback.format_exc())
            return False

    async def upsert_user(
        self,
        user_id: int,
        full_name: str,
        phone: str | None = None,
        department: str | None = None,
        block: str | None = None,
        role: str | None = None,
        position: str = "сотрудник",
        is_confirmed: int = 0,
        is_admin: int = 0,
        is_active: int = 1
    ):
        """Создать/обновить пользователя."""
        await self.conn.execute(
            """
            INSERT INTO users (user_id, full_name, phone, department, block, role, position, is_confirmed, is_admin, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                full_name=excluded.full_name,
                phone=excluded.phone,
                department=excluded.department,
                block=excluded.block,
                role=excluded.role,
                position=excluded.position,
                is_confirmed=excluded.is_confirmed,
                is_admin=excluded.is_admin,
                is_active=excluded.is_active,
                updated_at=CURRENT_TIMESTAMP;
            """,
            (user_id, full_name, phone, department, block, role, position, is_confirmed, is_admin, is_active)
        )
        await self.conn.commit()

    async def list_users(self) -> List[Dict]:
        cur = await self.conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def set_user_confirmed(self, user_id: int, confirmed: int = 1):
        await self.conn.execute("UPDATE users SET is_confirmed=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (confirmed, user_id))
        await self.conn.commit()

    async def set_user_admin(self, user_id: int, is_admin: int = 1):
        await self.conn.execute("UPDATE users SET is_admin=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (is_admin, user_id))
        await self.conn.commit()

    async def set_user_active(self, user_id: int, is_active: int = 1):
        await self.conn.execute("UPDATE users SET is_active=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (is_active, user_id))
        await self.conn.commit()
    # ---------- REGISTRATION V2 HELPERS ----------
    async def add_unconfirmed_user(
        self,
        user_id: int,
        full_name: str,
        phone: str | None = None,
        department: str | None = None,
        block: str | None = None,
        role: str | None = None,
    ) -> None:
        """
        Создаёт/обновляет пользователя как НЕ подтверждённого (is_confirmed=0).
        Используется в registration_v2.py при отправке заявки админам.
        """
        # position оставляем "сотрудник" (по умолчанию)
        await self.upsert_user(
            user_id=user_id,
            full_name=full_name or f"Пользователь {user_id}",
            phone=phone,
            department=department,
            block=block,
            role=role,
            position="сотрудник",
            is_confirmed=0,
            is_admin=0,
            is_active=1,
        )

    async def confirm_user(
        self,
        user_id: int,
        department: str | None = None,
        block: str | None = None,
        role: str | None = None,
    ) -> None:
        """
        Подтверждает пользователя (is_confirmed=1) и при необходимости обновляет department/block/role.
        Используется в registration_v2.py при подтверждении админом.
        """
        # Если вдруг пользователя нет (на всякий случай) — создадим минимальную запись
        u = await self.get_user(user_id)
        if not u:
            await self.upsert_user(
                user_id=user_id,
                full_name=f"Пользователь {user_id}",
                phone=None,
                department=department,
                block=block,
                role=role,
                position="сотрудник",
                is_confirmed=1,
                is_admin=0,
                is_active=1,
            )
            return

        # Обновляем поля и подтверждаем
        await self.conn.execute(
            """
            UPDATE users
               SET is_confirmed = 1,
                   department   = COALESCE(?, department),
                   block        = COALESCE(?, block),
                   role         = COALESCE(?, role),
                   is_active    = 1,
                   updated_at   = CURRENT_TIMESTAMP
             WHERE user_id = ?
            """,
            (department, block, role, user_id),
        )
        await self.conn.commit()

    async def set_position(self, user_id: int, position: str) -> None:
        """
        Устанавливает уровень доступа (position).
        Используется в registration_v2.py после выбора админом.
        """
        await self.conn.execute(
            "UPDATE users SET position=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=?",
            (position, user_id),
        )
        await self.conn.commit()

    # ---------- MILK PRICES ----------
    async def get_milk_prices(self, location: str) -> Dict[str, float]:
        base = dict(MILK_PRICE_DEFAULTS.get(location, {}))
        cur = await self.conn.execute(
            "SELECT counterparty, price FROM milk_prices WHERE location=?",
            (location,),
        )
        rows = await cur.fetchall()
        await cur.close()
        for r in rows:
            base[str(r["counterparty"])] = float(r["price"])
        return base

    async def set_milk_price(
        self,
        location: str,
        counterparty: str,
        price: float,
        changed_by: int | None = None,
    ) -> None:
        cur = await self.conn.execute(
            "SELECT price FROM milk_prices WHERE location=? AND counterparty=? LIMIT 1",
            (location, counterparty),
        )
        row = await cur.fetchone()
        await cur.close()
        old_price = float(row["price"]) if row else None
        new_price = float(price)

        await self.conn.execute(
            """
            INSERT INTO milk_prices (location, counterparty, price, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(location, counterparty) DO UPDATE SET
                price = excluded.price,
                updated_at = CURRENT_TIMESTAMP
            """,
            (location, counterparty, new_price),
        )
        await self.conn.execute(
            """
            INSERT INTO milk_price_logs (location, counterparty, old_price, new_price, changed_by)
            VALUES (?, ?, ?, ?, ?)
            """,
            (location, counterparty, old_price, new_price, changed_by),
        )
        await self.conn.commit()

    async def list_milk_price_logs(self, limit: int = 20) -> List[Dict]:
        cur = await self.conn.execute(
            """
            SELECT
                l.id,
                l.location,
                l.counterparty,
                l.old_price,
                l.new_price,
                l.changed_by,
                l.changed_at,
                u.full_name AS changed_by_name
            FROM milk_price_logs l
            LEFT JOIN users u ON u.user_id = l.changed_by
            ORDER BY l.changed_at DESC, l.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    # ---------- TASKS ----------
    async def create_task(
        self,
        title: str,
        description: str,
        assigned_by: int,
        assigned_to: int,
        deadline: str,
        priority: int = 1,
        file_id: str | None = None,
        file_type: str | None = None
    ) -> int:
        cur = await self.conn.execute(
            """
            INSERT INTO tasks (title, description, assigned_by, assigned_to, deadline, priority, file_id, file_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, description, assigned_by, assigned_to, deadline, priority, file_id, file_type)
        )
        await self.conn.commit()
        return cur.lastrowid

    async def update_task_status(self, task_id: int, status: str):
        await self.conn.execute(
            "UPDATE tasks SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, task_id)
        )
        await self.conn.commit()

    async def list_tasks_for_user(self, user_id: int) -> List[Dict]:
        cur = await self.conn.execute(
            "SELECT * FROM tasks WHERE assigned_to=? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def list_all_tasks(self) -> List[Dict]:
        cur = await self.conn.execute("SELECT * FROM tasks ORDER BY created_at DESC")
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def get_task(self, task_id: int) -> Optional[Dict]:
        cur = await self.conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    # ---------- REPORTS ----------
    async def add_report(self, user_id: int, text: str, date: str | None = None):
        if date:
            await self.conn.execute(
                "INSERT INTO reports (user_id, date, text) VALUES (?, ?, ?)",
                (user_id, date, text)
            )
        else:
            await self.conn.execute(
                "INSERT INTO reports (user_id, text) VALUES (?, ?)",
                (user_id, text)
            )
        await self.conn.commit()

    async def list_reports(self, limit: int = 50) -> List[Dict]:
        cur = await self.conn.execute(
            "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    # ---------- DOCUMENTS ----------
    async def add_document(
        self,
        title: str,
        description: str,
        file_id: str,
        file_type: str,
        category: str | None,
        department_id: int | None,
        created_by: int
    ):
        await self.conn.execute(
            """
            INSERT INTO documents (title, description, file_id, file_type, category, department_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (title, description, file_id, file_type, category, department_id, created_by)
        )
        await self.conn.commit()

    async def list_documents(self, category: str | None = None, limit: int = 50) -> List[Dict]:
        if category:
            cur = await self.conn.execute(
                "SELECT * FROM documents WHERE category=? ORDER BY created_at DESC LIMIT ?",
                (category, limit)
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    # ---------- FINES ----------
    async def add_fine(self, user_id: int, amount: int, reason: str, created_by: int, task_id: int | None = None):
        await self.conn.execute(
            "INSERT INTO fines (user_id, amount, reason, task_id, created_by) VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, reason, task_id, created_by)
        )
        await self.conn.commit()

    async def list_fines(self, status: str | None = None, limit: int = 100) -> List[Dict]:
        if status:
            cur = await self.conn.execute(
                "SELECT * FROM fines WHERE status=? ORDER BY created_at DESC LIMIT ?",
                (status, limit)
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM fines ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def set_fine_status(self, fine_id: int, status: str):
        await self.conn.execute(
            "UPDATE fines SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (status, fine_id)
        )
        await self.conn.commit()

    # ---------- MTP DIRECTORY ----------
    async def add_mtp_directory_item(
        self,
        unit_name: str,
        equipment_name: str,
        inv_number: str,
        year: Optional[str],
        responsible: str,
        comment: Optional[str],
        created_by: int,
    ):
        await self.conn.execute(
            """
            INSERT INTO mtp_directory (unit_name, equipment_name, inv_number, year, responsible, comment, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                unit_name,
                equipment_name,
                inv_number,
                year,
                responsible,
                comment,
                created_by,
            ),
        )
        await self.conn.commit()

    async def list_mtp_directory_items(self, limit: int = 50):
        cur = await self.conn.execute(
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

    # ---------- HELPERS ----------
    async def is_admin(self, user_id: int) -> bool:
        u = await self.get_user(user_id)
        return bool(u and u["is_admin"])

    async def execute_query(self, query: str, params: tuple = ()) -> Optional[List[Dict]]:
        try:
            cur = await self.conn.execute(query, params)
            if query.lstrip().upper().startswith("SELECT"):
                rows = await cur.fetchall()
                await cur.close()
                return [dict(r) for r in rows]
            await self.conn.commit()
            return None
        except Exception:
            logger.error("❌ SQL error:\n%s\n%s", query, traceback.format_exc())
            return None

    async def close(self):
        if self.conn:
            await self.conn.close()
            logger.info("🔌 БД соединение закрыто")


# ---------- глобальный экземпляр ----------
db = Database()


async def init_db():
    await db.connect()
    from config import ADMIN_IDS

    for admin_id in ADMIN_IDS:
        u = await db.get_user(admin_id)
        if not u:
            await db.conn.execute(
                """
                INSERT INTO users (user_id, full_name, is_admin, is_confirmed)
                VALUES (?, ?, 1, 1);
                """,
                (admin_id, f"Администратор {admin_id}"),
            )
        else:
            await db.conn.execute(
                "UPDATE users SET is_admin=1, is_confirmed=1 WHERE user_id=?",
                (admin_id,),
            )
    await db.conn.commit()
    if ADMIN_IDS:
        logger.info("✅ Администраторы инициализированы: %s", ADMIN_IDS)
