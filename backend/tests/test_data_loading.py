import geopandas as gpd
import pytest

from app.core.errors import DatasetCorruptError, DatasetNotAvailableError, RegionNotFoundError
from app.datasets import read_manifest
from app.schemas.common import Provenance
from app.services.roads import get_road_graph


def test_load_and_cache(repo, synthetic_region):
    a = repo.load("houston-sw-pilot", "tracts")
    b = repo.load("houston-sw-pilot", "tracts")
    assert a is b and len(a) == 4 and a.crs.to_epsg() == 4326


def test_cache_invalidated_on_rewrite(repo, synthetic_region):
    import os
    import time

    a = repo.load("houston-sw-pilot", "tracts")
    path = synthetic_region / "tracts.parquet"
    a.head(2).to_parquet(path)
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert len(repo.load("houston-sw-pilot", "tracts")) == 2


def test_missing_dataset_raises_with_hint(repo):
    with pytest.raises(DatasetNotAvailableError) as exc:
        repo.load("houston-sw-pilot", "tracts")
    assert "download_data.py" in exc.value.details["hint"]


def test_unknown_region(repo):
    with pytest.raises(RegionNotFoundError):
        repo.load("atlantis", "tracts")


def test_missing_required_columns(repo, synthetic_region):
    path = synthetic_region / "facilities.parquet"
    gpd.read_parquet(path).drop(columns=["verification_status"]).to_parquet(path)
    with pytest.raises(DatasetCorruptError):
        repo.load("houston-sw-pilot", "facilities")


def test_manifest_provenance_is_synthetic(repo, synthetic_region):
    manifest = read_manifest(synthetic_region)
    assert all(e["provenance"] == "synthetic" for e in manifest["datasets"].values())
    assert repo.provenance("houston-sw-pilot", "tracts") is Provenance.synthetic


def test_road_graph_loader(repo, synthetic_region):
    G = get_road_graph(repo, "houston-sw-pilot")
    assert G.number_of_nodes() == 9
    assert get_road_graph(repo, "houston-sw-pilot") is G
