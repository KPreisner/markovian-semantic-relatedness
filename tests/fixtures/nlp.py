"""A stand-in spaCy pipeline for tests: a blank English tokenizer plus an entity ruler, saved to
disk nested the way an unpacked model wheel is."""

from pathlib import Path

import spacy

PATTERNS = [
    {"label": "PERSON", "pattern": "Bill G"},
    {"label": "DATE", "pattern": "September 19, 1979"},
    {"label": "PERSON", "pattern": "Louis Armstrong"},
]


def save_toy_pipeline(root: Path) -> Path:
    """Save it under `root/en_toy/en_toy-0.0.1/` and return `root/en_toy`."""
    nlp = spacy.blank("en")
    nlp.meta.update({"name": "toy", "version": "0.0.1"})
    ruler = nlp.add_pipe("entity_ruler", name="ner")
    ruler.add_patterns(PATTERNS)  # type: ignore[attr-defined]
    (root / "en_toy").mkdir(parents=True)
    nlp.to_disk(root / "en_toy" / "en_toy-0.0.1")
    return root / "en_toy"
