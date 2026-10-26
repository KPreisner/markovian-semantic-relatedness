from datetime import datetime

from msr_api.schemas import Schema


class Corpus(Schema):
    corpus_id: str
    description: str
    formats: list[str]
    text_field: str
    id_field: str
    file_count: int
    byte_count: int
    created_at: datetime
    updated_at: datetime
