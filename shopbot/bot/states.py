from aiogram.fsm.state import State, StatesGroup


class DepositStates(StatesGroup):
    custom_amount = State()


class CategoryForm(StatesGroup):
    name = State()


class ProductForm(StatesGroup):
    name = State()
    description = State()
    price = State()
    delivery_type = State()
    static_content = State()


class ProductEdit(StatesGroup):
    value = State()


class StockUpload(StatesGroup):
    items = State()


class UserAdmin(StatesGroup):
    search = State()
    balance = State()


class BroadcastForm(StatesGroup):
    message = State()
    confirm = State()
