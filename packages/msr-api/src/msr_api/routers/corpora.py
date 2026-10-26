from fastapi import APIRouter

from msr_api.dependencies import Connection
from msr_api.schemas.corpora import Corpus
from msr_db.registry import AsyncCorpusRepository

router = APIRouter(prefix="/corpora", tags=["corpora"])


@router.get("")
async def list_corpora(conn: Connection) -> list[Corpus]:
    return [
        Corpus(
            corpus_id=r.corpus_id,
            description=r.description,
            formats=r.formats,
            text_field=r.text_field,
            id_field=r.id_field,
            file_count=r.file_count,
            byte_count=r.byte_count,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in await AsyncCorpusRepository(conn).all()
    ]
