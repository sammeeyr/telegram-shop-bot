from aiogram import Router

from shopbot.bot.filters import IsAdmin
from shopbot.bot.handlers.admin import broadcast, catalog, menu, reports, stock, users


def build_admin_router() -> Router:
    router = Router(name="admin")
    # Filters on the parent gate every admin sub-router.
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())
    router.include_routers(menu.router, catalog.router, stock.router, users.router, reports.router, broadcast.router)
    return router
