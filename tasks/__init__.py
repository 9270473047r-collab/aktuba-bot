from aiogram import Router

# ── импортируем подпакеты ─────────────────────────────────────
from .create              import router as create_router
from .admin_users_router  import router as admin_users_router
from .actions             import router as actions_router
from .progress            import router as progress_router
from .view                import router as view_router
from .profile             import router as profile_router
from .report              import router as report_router
from .menu_router         import router as menu_router
from .all_tasks_pdf       import router as all_tasks_pdf_router

# ── единый список ────────────────────────────────────────────
routers: list[Router] = [
    admin_users_router,
    all_tasks_pdf_router,
    create_router,
    actions_router,      # callback-хендлеры управления задачами
    
    progress_router,
    view_router,
    profile_router,
    report_router,
    menu_router,
]
