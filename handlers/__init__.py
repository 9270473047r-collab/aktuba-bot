# aktuba_bot/handlers/__init__.py

from .user_management import router as user_management_router
from .common import router as common_router
from .registration_v2 import router as registration_router
from .reports import router as reports_router
from .kpi import router as kpi_router
from .org import router as org_router
from .reglament import router as reglament_router
from .admin import router as admin_router
from .ai_chat import router as ai_chat_router
from .admin_heads import router as admin_heads_router

# ВАЖНО: herd_movement оставляем v2 (как у вас)
from .prod.herd_movement_v2 import router as herd_movement_router

from .mtp_summary import router as mtp_summary_router

# ВАЖНО: milk_summary подключаем НЕ v2, а новый handlers/milk_summary.py
from .milk_summary import router as milk_summary_router

from .soyuz_agro import router as soyuz_agro_router

from .prod.report_submit import router as prod_submit_router
from .prod.report_view import router as prod_view_router

from .vet.report_submit import router as vet_submit_router
from .vet.report_view import router as vet_view_router

from .eng.report_submit import router as eng_submit_router
from .eng.report_view import router as eng_view_router

from .adm.report_submit import router as adm_submit_router
from .adm.report_view import router as adm_view_router

from .acc.report_submit import router as acc_submit_router
from .acc.report_view import router as acc_view_router

from .saf.report_submit import router as saf_submit_router
from .saf.report_view import router as saf_view_router


routers = [
    user_management_router,
    mtp_summary_router,
    herd_movement_router,
    common_router,
    registration_router,
    reports_router,
    kpi_router,
    org_router,
    reglament_router,
    admin_router,
    ai_chat_router,
    admin_heads_router,

    milk_summary_router,
    soyuz_agro_router,

    prod_submit_router, prod_view_router,
    vet_submit_router, vet_view_router,
    eng_submit_router, eng_view_router,
    adm_submit_router, adm_view_router,
    acc_submit_router, acc_view_router,
    saf_submit_router, saf_view_router,
]
