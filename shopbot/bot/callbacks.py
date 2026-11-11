"""Typed inline-button callback payloads (each must pack to <= 64 bytes)."""
from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="nav"):
    to: str  # shop / profile / topup / noop


class CategoryCb(CallbackData, prefix="cat"):
    id: int


class ProductCb(CallbackData, prefix="prd"):
    id: int


class QtyCb(CallbackData, prefix="qty"):
    id: int
    qty: int


class BuyCb(CallbackData, prefix="buy"):
    id: int
    qty: int
    price: int  # unit price the user saw; purchase is rejected if it changed


class OrdersPage(CallbackData, prefix="ords"):
    page: int


class OrderCb(CallbackData, prefix="ord"):
    id: int
    action: str = "view"  # view / items
    page: int = 0


class TopUpCb(CallbackData, prefix="top"):
    amount: int  # cents; 0 = custom amount


class DepositCb(CallbackData, prefix="dep"):
    id: int
    action: str  # view / check / cancel


class DepositsPage(CallbackData, prefix="deps"):
    page: int


class Adm(CallbackData, prefix="adm"):
    act: str
    id: int = 0
    page: int = 0
