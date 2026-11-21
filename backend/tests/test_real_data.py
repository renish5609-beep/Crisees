"""Checks against the REAL processed datasets, if they have been generated.

Skipped automatically when data/processed/houston-sw-pilot/ is absent (e.g. CI
without network). Run the pipeline first to exercise these.
"""

import pytest

from app.core.config import get_settings
from app.services.repository import DataRepository
from app.services.roads import get_road_graph
from pipeline.context import PipelineContext
from pipeline.validate import validate

settings = get_settings()
REAL = settings.processed_dir / "houston-sw-pilot" / "manifest.json"
pytestmark = pytest.mark.skipif(not REAL.exists(), reason="real processed data not generated")


def test_real_datasets_validate():
    results = validate(PipelineContext.for_region("houston-sw-pilot", settings=settings))
    failures = {r.dataset: r.errors for r in results if not r.ok}
    assert not failures


def test_real_data_is_not_synthetic():
    repo = DataRepository(settings)
    for key in ("tracts", "demographics", "road_edges", "facilities", "flood_hazards"):
        assert repo.provenance("houston-sw-pilot", key).value in ("real", "derived")


def test_real_graph_mostly_strongly_connected():
    import networkx as nx

    G = get_road_graph(DataRepository(settings), "houston-sw-pilot")
    largest = max(nx.strongly_connected_components(G), key=len)
    assert len(largest) / G.number_of_nodes() > 0.9
