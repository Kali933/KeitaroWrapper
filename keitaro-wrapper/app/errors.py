"""Ошибки приложения. main.py превращает их в понятные HTTP-ответы."""


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(AppError):
    status_code = 404


class ForbiddenError(AppError):
    status_code = 403


class ConflictError(AppError):
    status_code = 409


class KeitaroError(AppError):
    """Keitaro недоступен или вернул ошибку."""

    status_code = 502
