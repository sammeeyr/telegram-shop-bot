class CommerceError(Exception):
    status_code = 400


class ResourceNotFound(CommerceError):
    status_code = 404


class Conflict(CommerceError):
    status_code = 409


class InsufficientStock(Conflict):
    pass


class IdempotencyConflict(Conflict):
    pass


class InvalidQuantity(CommerceError):
    status_code = 422


class PaymentRequired(Conflict):
    pass