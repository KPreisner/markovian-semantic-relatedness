from typing import Literal

from msr_api.schemas import Schema


class Health(Schema):
    status: Literal["ok", "degraded"]
    checks: dict[str, str]
