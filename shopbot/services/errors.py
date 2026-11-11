"""Business errors. Their messages are safe to show to end users."""
from __future__ import annotations


class ShopError(Exception):
    pass


class NotFound(ShopError):
    pass


class ProductUnavailable(ShopError):
    def __init__(self) -> None:
        super().__init__("This product is no longer available.")


class OutOfStock(ShopError):
    def __init__(self, available: int) -> None:
        self.available = available
        super().__init__("Out of stock." if available <= 0 else f"Only {available} left in stock.")


class InsufficientBalance(ShopError):
    def __init__(self, required: int, balance: int) -> None:
        self.required = required
        self.balance = balance
        super().__init__("Insufficient balance.")


class InvalidQuantity(ShopError):
    pass


class PriceChanged(ShopError):
    def __init__(self) -> None:
        super().__init__("The price has changed. Please review your order again.")
