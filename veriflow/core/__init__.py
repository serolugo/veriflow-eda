class VeriFlowError(Exception):
    """Hard error — stops execution and prints [ERROR] message."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "VF_ERROR",
        details: dict | None = None,
        exit_code: int = 1,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details
        self.exit_code = exit_code

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "exit_code": self.exit_code,
        }
