"""spaCy pipelines, loaded by path from `data/nlp/` rather than installed as packages."""

from dataclasses import dataclass
from pathlib import Path

import spacy
from spacy.language import Language
from spacy.pipeline import Tok2Vec


@dataclass(frozen=True)
class PipelineInfo:
    name: str
    """e.g. `en_core_web_lg`."""
    version: str
    lang: str

    @property
    def slug(self) -> str:
        """e.g. `en_core_web_lg-3.8.0`, used in output paths."""
        return f"{self.name}-{self.version}"


def find_pipeline_dir(path: Path) -> Path:
    """The one directory at or under `path` holding a pipeline's `config.cfg`.

    An unpacked spaCy model wheel nests it (`en_core_web_lg/en_core_web_lg-3.8.0/`), so the
    exact layout doesn't matter.
    """
    found = sorted(p.parent for p in path.rglob("config.cfg") if (p.parent / "meta.json").exists())
    if len(found) != 1:
        raise FileNotFoundError(
            f"expected one spaCy pipeline (config.cfg + meta.json) under {path}, found {len(found)}"
        )
    return found[0]


def load_pipeline(path: Path) -> Language:
    """Load a pipeline with only what term sets need: the tokenizer and NER.

    Tagger, parser, lemmatizer, and attribute ruler are disabled. The shared tok2vec stays only if
    NER listens to it.
    """
    nlp = spacy.load(find_pipeline_dir(path))
    keep = {"ner"}
    if "tok2vec" in nlp.pipe_names:
        tok2vec = nlp.get_pipe("tok2vec")
        if isinstance(tok2vec, Tok2Vec) and "ner" in tok2vec.listening_components:
            keep.add("tok2vec")
    for name in nlp.pipe_names:
        if name not in keep:
            nlp.disable_pipe(name)
    return nlp


def pipeline_info(nlp: Language) -> PipelineInfo:
    meta = nlp.meta
    return PipelineInfo(
        name=f"{meta['lang']}_{meta['name']}", version=str(meta["version"]), lang=meta["lang"]
    )
