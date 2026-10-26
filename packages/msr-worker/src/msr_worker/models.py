"""Loaded models, kept across tasks. Loading a model takes seconds for the small model and minutes
(tens of GB) for a full Wikipedia one, so each worker process keeps the most recently used few
(`MSR_WORKER_MODEL_CACHE`, default 1). A model id is never reused, so a cached model can't go
stale."""

import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from msr.model.artifacts import MANIFEST, load_model, load_references, references_dir
from msr.model.build import Model
from msr.model.references import References
from msr_worker.errors import JobFailedError

log = structlog.get_logger(__name__)


@dataclass
class LoadedModel:
    model_id: str
    directory: Path
    model: Model
    _references: dict[str, References] = field(default_factory=dict)

    def references(self, strategy: object) -> References:
        """A strategy's X′, loaded on first use."""
        key = str(strategy)
        if key not in self._references:
            if not (references_dir(self.directory, strategy) / "refs.json").exists():
                raise JobFailedError(
                    "refs_not_built", f"model {self.model_id!r} has no X′ for {key!r}"
                )
            self._references[key] = load_references(self.directory, strategy)
        return self._references[key]


class ModelCache:
    def __init__(self, models_dir: Path, size: int) -> None:
        self.models_dir = models_dir
        self.size = size
        self._models: OrderedDict[str, LoadedModel] = OrderedDict()

    def get(self, model_id: str) -> LoadedModel:
        if model_id in self._models:
            self._models.move_to_end(model_id)
            return self._models[model_id]
        directory = self.models_dir / model_id
        if not (directory / MANIFEST).exists():
            raise JobFailedError("model_missing", f"model {model_id!r} isn't on this worker's disk")
        while len(self._models) >= self.size:
            evicted, _ = self._models.popitem(last=False)
            log.info("model_evicted", model_id=evicted)
        start = time.monotonic()
        loaded = LoadedModel(model_id, directory, load_model(directory))
        log.info("model_loaded", model_id=model_id, seconds=round(time.monotonic() - start, 2))
        self._models[model_id] = loaded
        return loaded
