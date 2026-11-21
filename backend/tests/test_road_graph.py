import networkx as nx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from shapely import wkb
from shapely.geometry import LineString

from app.services.road_graph import graph_to_tables, tables_to_graph
from pipeline.processing.roads import (
    finalize_graph,
    overture_to_graph,
    parse_maxspeed_kph,
    stable_node_id,
)
from tests.fixtures.synthetic import synthetic_graph


def test_roundtrip_preserves_topology_and_attributes():
    G = synthetic_graph()
    nodes, edges = graph_to_tables(G)
    assert nodes.crs.to_epsg() == 4326 and edges.crs.to_epsg() == 4326
    H = tables_to_graph(nodes, edges)
    assert set(H.nodes) == set(G.nodes)
    assert set(H.edges(keys=True)) == set(G.edges(keys=True))
    for u, v, k, d in G.edges(keys=True, data=True):
        h = H.edges[u, v, k]
        assert h["length"] == d["length"] and h["oneway"] == d["oneway"] and h["highway"] == d["highway"]
        assert h["geometry"].equals(d["geometry"])
    for n, d in G.nodes(data=True):
        assert (H.nodes[n]["x"], H.nodes[n]["y"]) == (d["x"], d["y"])
    assert H.graph["crs"] == "EPSG:4326"


def test_directionality_one_way_edge_has_no_reverse():
    G = synthetic_graph()
    H = tables_to_graph(*graph_to_tables(G))
    assert H.has_edge(1020, 1021) and not H.has_edge(1021, 1020)
    assert H.has_edge(1000, 1001) and H.has_edge(1001, 1000)


def test_reconstructed_graph_supports_routing():
    H = tables_to_graph(*graph_to_tables(synthetic_graph()))
    assert nx.shortest_path_length(H, 1000, 1022, weight="length") == pytest.approx(4 * 964.0)
    assert nx.is_strongly_connected(H)


def test_osmnx_compatibility():
    import osmnx as ox

    H = tables_to_graph(*graph_to_tables(synthetic_graph()))
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(H)
    assert len(gdf_nodes) == 9 and len(gdf_edges) == H.number_of_edges()
    assert ox.routing.shortest_path(H, 1000, 1022, weight="length")[0] == 1000
    assert ox.stats.basic_stats(H)["n"] == 9


def test_missing_node_reference_raises():
    nodes, edges = graph_to_tables(synthetic_graph())
    with pytest.raises(ValueError, match="missing node"):
        tables_to_graph(nodes[nodes.node_id != 1000], edges)


@pytest.mark.parametrize("raw,kph", [("35 mph", 56.3), ("50", 50.0), ("60 km/h", 60.0), (["30 mph", "40 mph"], 56.4),
                                     (None, None), ("signals", None)])
def test_parse_maxspeed(raw, kph):
    assert parse_maxspeed_kph(raw) == kph


def _write_overture(path):
    """SYNTHETIC Overture-shaped segments."""
    def seg(i, coords, conns, cls="residential", restrictions=None, subclass=None, subtype="road"):
        return {
            "id": f"seg-{i}", "geometry": wkb.dumps(LineString(coords)), "names": {"primary": f"Syn {i}"},
            "subtype": subtype, "class": cls, "subclass": subclass,
            "connectors": [{"connector_id": c, "at": a} for c, a in conns],
            "access_restrictions": restrictions, "speed_limits": None, "road_flags": None,
            "sources": [{"record_id": f"w{100 + i}@1", "dataset": "OpenStreetMap"}],
        }
    a, b, c, d = ("aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002",
                  "cccccccc-0000-0000-0000-000000000003", "dddddddd-0000-0000-0000-000000000004")
    oneway_back = [{"access_type": "denied", "when": {"heading": "backward", "mode": None, "during": None,
                                                       "using": None}, "between": None}]
    rows = [
        seg(1, [(-95.60, 29.62), (-95.59, 29.62), (-95.58, 29.62)], [(a, 0.0), (b, 0.5), (c, 1.0)]),
        seg(2, [(-95.59, 29.62), (-95.59, 29.63)], [(b, 0.0), (d, 1.0)], cls="primary", restrictions=oneway_back),
        seg(3, [(-95.58, 29.62), (-95.58, 29.63)], [(c, 0.0), (d, 1.0)], cls="service", subclass="driveway"),
        seg(4, [(-95.60, 29.62), (-95.60, 29.63)], [(a, 0.0), (d, 1.0)], subtype="rail", cls="standard_gauge"),
    ]
    pq.write_table(pa.Table.from_pylist(rows), path)
    return a, b, c, d


def test_overture_conversion_splits_and_orients(tmp_path):
    p = tmp_path / "segments.parquet"
    a, b, c, d = _write_overture(p)
    G, stats = overture_to_graph(p, "EPSG:32615")
    ida, idb, idc, idd = (stable_node_id(x) for x in (a, b, c, d))
    # seg-1 split at its middle connector into two two-way edges (4 directed)
    assert G.has_edge(ida, idb) and G.has_edge(idb, ida) and G.has_edge(idb, idc)
    # seg-2 one-way forward only
    assert G.has_edge(idb, idd) and not G.has_edge(idd, idb)
    # driveway and rail excluded
    assert not G.has_edge(idc, idd) and not G.has_edge(ida, idd)
    e = G.edges[ida, idb, 0]
    assert e["length"] == pytest.approx(968, rel=0.01)  # 0.01 deg lon at 29.62N
    assert e["osmid"] == 101 and G.edges[idb, idd, 0]["oneway"] is True
    G2, _ = finalize_graph(G)
    assert G2.nodes[idb]["street_count"] == 3
    nodes, edges = graph_to_tables(G2)
    assert set(edges["osm_way_ids"].explode()) == {101, 102}
