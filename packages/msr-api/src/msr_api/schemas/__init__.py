"""Request and response models (the OpenAPI schema the BFF's client is generated from)."""

from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    # Responses always include defaulted fields, so their schema marks them required (generated
    # clients then type them as present). Request schemas are unaffected.
    model_config = ConfigDict(
        frozen=True, extra="forbid", json_schema_serialization_defaults_required=True
    )
