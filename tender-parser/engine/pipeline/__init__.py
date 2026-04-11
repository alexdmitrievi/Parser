"""Pipeline: orchestration, deduplication, versioning, tagging."""

from engine.pipeline.orchestrator import PipelineOrchestrator
from engine.pipeline.deduplicator import Deduplicator
from engine.pipeline.versioner import ChangeDetector
from engine.pipeline.tagger import NicheTagger

__all__ = [
    "PipelineOrchestrator",
    "Deduplicator",
    "ChangeDetector",
    "NicheTagger",
]
