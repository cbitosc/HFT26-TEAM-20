"""Domain errors. Each carries the HTTP status and a stable machine-readable code."""


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: list[dict] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404

    def __init__(self, resource: str, identifier: str):
        self.code = f"{resource.upper()}_NOT_FOUND"
        super().__init__(f"{resource.capitalize()} '{str(identifier)[:64]}' was not found.")


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"


class InvalidTransitionError(ConflictError):
    code = "INVALID_TRANSITION"
