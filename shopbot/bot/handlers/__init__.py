from aiogram import Router

from shopbot.bot.handlers import deposit, fallback, orders, shop, start
from shopbot.bot.handlers.admin import build_admin_router


def build_root_router() -> Router:
    """Order matters: menu buttons/commands first, catch-alls last."""
    root = Router(name="root")
    root.include_routers(start.router, shop.router, orders.router, deposit.router, build_admin_router(), fallback.router)
    return root
