from typing import Any

from psycopg import AsyncConnection

from msr_api.core.errors import NotFoundError
from msr_api.schemas.models import ModelDetail, ModelSummary
from msr_db.registry import AsyncModelRepository
from msr_db.rows import ModelRow


def summarize(row: ModelRow) -> ModelSummary:
    """The provenance a model picker shows, read from the manifest."""
    manifest = row.manifest
    build: dict[str, Any] = manifest.get("build", {})
    parse: dict[str, Any] = build.get("parse", {})
    return ModelSummary(
        model_id=row.model_id,
        model_name=row.model_name,
        description=row.description,
        term_count=row.term_count,
        reference_steps=manifest.get("reference_steps", {}),
        stop_words=manifest.get("params", {}).get("stop_words"),
        source=build.get("source"),
        pipeline=build.get("pipeline"),
        pipeline_version=build.get("pipeline_version"),
        parts_used=build.get("max_parts"),
        parts_total=parse.get("parts"),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_model(conn: AsyncConnection[Any], model_id: str) -> ModelRow:
    row = await AsyncModelRepository(conn).get(model_id)
    if row is None:
        raise NotFoundError(f"no model {model_id!r}", code="model_not_found")
    return row


def detail(row: ModelRow) -> ModelDetail:
    return ModelDetail(**summarize(row).model_dump(), manifest=row.manifest)
