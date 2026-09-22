class AppError(Exception):
    def __init__(self, status_code: int, message: str, code: int = 0):
        self.status_code = status_code
        self.message = message
        self.code = code
        super().__init__(message)


class Unauthorized(AppError):
    def __init__(self, message: str = "未登录或登录已失效"):
        super().__init__(401, message)


class Forbidden(AppError):
    def __init__(self, message: str = "无权执行该操作"):
        super().__init__(403, message)


class NotFound(AppError):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(404, message)


class Conflict(AppError):
    def __init__(self, message: str):
        super().__init__(409, message)

