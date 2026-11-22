"""Engine A: routing on small graphs with hand-computed answers."""

import numpy as np
import pandas as pd
import pytest

from app.engine.network import (
    CLASS_SPEED_KPH,
    RoadNetwork,
    SpeedModel,
    component_stats,
    costs_to_targets,
    nearest_target,
    shortest_path,
    travel_costs,
)

# Nodes on a line, ~1 km apart near Houston (positions only matter for snapping).
LON0, LAT0 = -95.60, 29.62


def make_net(edge_rows, n_nodes=5, speed_model=None):
    nodes = pd.DataFrame({"node_id": np.arange(n_nodes) + 100, "lon": LON0 + np.arange(n_nodes) * 0.01,
                          "lat": np.full(n_nodes, LAT0)})
    rows = []
    for i, r in enumerate(edge_rows):
        u, v, length, cls = r[:4]
        speed = r[4] if len(r) > 4 else None
        rows.append({"edge_id": f"{u}-{v}-{i}", "u": u + 100, "v": v + 100, "length_m": float(length),
                     "road_class": cls, "maxspeed_kph": speed, "source_ref": f"seg{min(u, v)}{max(u, v)}"})
    return RoadNetwork.from_tables(nodes, pd.DataFrame(rows), "EPSG:32615", speed_model)


def residential_min(m):  # minutes at the residential class speed
    return m / (CLASS_SPEED_KPH["residential"] * 1000 / 60)


def test_shortest_path_known_answer():
    # 0-1-2 chain (1000 m each) vs direct 0-2 (2500 m): chain wins.
    net = make_net([(0, 1, 1000, "residential"), (1, 2, 1000, "residential"), (0, 2, 2500, "residential")])
    cost, path = shortest_path(net.drive_length_matrix(), 0, 2)
    assert cost == pytest.approx(2000) and path == [0, 1, 2]


def test_one_way_is_respected():
    net = make_net([(0, 1, 1000, "residential"), (1, 0, 5000, "residential")])
    m = net.drive_length_matrix()
    assert shortest_path(m, 0, 1)[0] == pytest.approx(1000)
    assert shortest_path(m, 1, 0)[0] == pytest.approx(5000)  # must use the other directed edge
    net2 = make_net([(0, 1, 1000, "residential")])
    assert shortest_path(net2.drive_length_matrix(), 1, 0) == (float("inf"), [])


def test_closure_reroutes_without_mutating_baseline():
    net = make_net([(0, 1, 1000, "residential"), (1, 2, 1000, "residential"), (0, 2, 2500, "residential")])
    before = net.length_m.copy()
    closed = np.zeros(net.n_edges, bool)
    closed[1] = True  # close 1->2
    cost, path = shortest_path(net.drive_length_matrix(closed), 0, 2)
    assert cost == pytest.approx(2500) and path == [0, 2]
    assert shortest_path(net.drive_length_matrix(), 0, 2)[0] == pytest.approx(2000)  # baseline intact
    np.testing.assert_array_equal(net.length_m, before)


def test_disconnected_component_is_inf_not_zero():
    net = make_net([(0, 1, 1000, "residential"), (3, 4, 1000, "residential")])
    d = travel_costs(net.drive_length_matrix(), np.array([0]))
    assert np.isinf(d[0, 3]) and np.isinf(d[0, 4]) and d[0, 0] == 0
    stats = component_stats(net.drive_matrix())
    assert stats["weak_components"] == 3  # {0,1}, {2}, {3,4}


def test_parallel_edges_take_minimum_not_sum():
    net = make_net([(0, 1, 1000, "residential"), (0, 1, 400, "residential")])
    assert shortest_path(net.drive_length_matrix(), 0, 1)[0] == pytest.approx(400)


def test_travel_time_posted_vs_class_default():
    net = make_net([(0, 1, 1000, "primary", 60.0), (1, 2, 1000, "primary", None), (2, 3, 1000, "primary", 400.0)])
    assert net.speed_source.tolist() == ["posted", "class_default", "class_default"]  # 400 km/h unreliable
    assert net.time_min[0] == pytest.approx(1.0)  # 1 km at 60 km/h
    assert net.time_min[1] == pytest.approx(1000 / (CLASS_SPEED_KPH["primary"] * 1000 / 60))
    slow = make_net([(0, 1, 1000, "primary", 60.0)], speed_model=SpeedModel(speed_factor=0.5))
    assert slow.time_min[0] == pytest.approx(2.0)


def test_walk_network_is_undirected_and_excludes_motorways():
    net = make_net([(0, 1, 1000, "residential"), (1, 2, 1000, "motorway"), (2, 3, 300, "residential")])
    w = net.walk_matrix()
    assert shortest_path(w, 1, 0)[0] == pytest.approx(1000)  # against one-way direction is fine on foot
    assert np.isinf(shortest_path(w, 0, 2)[0])  # motorway not walkable


def test_multi_target_functions_match_brute_force():
    edges = [(0, 1, 100, "residential"), (1, 2, 200, "residential"), (2, 3, 300, "residential"),
             (3, 4, 400, "residential"), (4, 0, 50, "residential")]
    net = make_net(edges)
    m = net.drive_length_matrix()
    full = travel_costs(m, np.arange(5))  # (5, 5) brute force
    targets = np.array([2, 4])
    to_t = costs_to_targets(m, targets)  # (T, N): node -> target
    np.testing.assert_allclose(to_t, full[:, targets].T)
    dist, src = nearest_target(m, targets)
    np.testing.assert_allclose(dist, full[:, targets].min(axis=1))
    assert set(np.unique(src)) <= set(targets)


def test_segment_closure_closes_both_directions():
    net = make_net([(0, 1, 1000, "residential"), (1, 0, 1000, "residential"), (1, 2, 500, "residential")])
    m = np.zeros(net.n_edges, bool)
    m[0] = True
    full = net.closure_mask_for_segments(m)
    assert full.tolist() == [True, True, False]


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        make_net([(0, 9, 100, "residential")])  # unknown node
    with pytest.raises(ValueError):
        make_net([(0, 1, -5, "residential")])
