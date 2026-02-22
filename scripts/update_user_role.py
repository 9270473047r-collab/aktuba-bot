#!/usr/bin/env python3
"""
Однократное обновление роли в БД по ФИО.
Запуск из корня проекта: python scripts/update_user_role.py
"""
import asyncio
import os
import sys

# чтобы импортировать db из корня проекта
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import db


async def main():
    await db.initialize()
    full_name = "Быстрова Резеда Миргаязовна"
    new_role = "плем учетчик"
    ok = await db.update_role_by_full_name(full_name, new_role)
    await db.close()
    if ok:
        print(f"✅ Роль обновлена: {full_name} → {new_role}")
    else:
        print(f"⚠️ Пользователь не найден в БД: {full_name}")


if __name__ == "__main__":
    asyncio.run(main())
