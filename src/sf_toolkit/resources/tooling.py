from typing import NamedTuple
from .base import ApiResource


class AnonExecResult(NamedTuple):
    line: int
    column: int
    compiled: bool
    success: bool
    compileProblem: str | None
    exceptionStackTrace: str | None
    exceptionMessage: str | None


class ToolingResource(ApiResource):
    def execute_anonymous(self, code: str):
        return AnonExecResult(
            **self.client.get(
                self.client.tooling_url + "/executeAnonymous",
                params={"anonymousBody": code},
            ).json()
        )
