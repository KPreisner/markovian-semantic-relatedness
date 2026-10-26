"""Request and response models (the OpenAPI schema the BFF's client is generated from)."""

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
