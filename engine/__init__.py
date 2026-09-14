"""Engine — production-grade scraping core for tender/auction/grant aggregation.

Public API:
    from engine import PipelineOrchestrator, BaseSourceAdapter, SourceConfig
    from engine.compat import run_adapter_legacy, run_adapter_full_pipeline
    from engine.sources.tenders.corporate import get_corporate_adapter, get_all_corporate_adapters
    from engine.sources.tenders.eis_api import get_eis_api_adapter
    from engine.sources.tenders.b2b_center import get_b2b_center_adapter
"""

from engine.types import SourceConfig, SourceCategory, FetchMethod, ParsedRecord
from engine.sources.base import BaseSourceAdapter
from engine.pipeline.orchestrator import PipelineOrchestrator
from engine.config.registry import get_registry

__all__ = [
    "SourceConfig",
    "SourceCategory",
    "FetchMethod",
    "ParsedRecord",
    "BaseSourceAdapter",
    "PipelineOrchestrator",
    "get_registry",
]
