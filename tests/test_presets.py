from __future__ import annotations

import ipaddress

import pytest

from netarchitect.core.design import analyze
from netarchitect.core.spec import PRESET_NAMES, load_preset


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_preset_analyzes_end_to_end(preset):
    analysis = analyze(load_preset(preset))
    assert analysis.export_filename == f"{preset}.txt"
    assert analysis.selected.decisions
    assert analysis.alternate.decisions
    assert analysis.device_configs


@pytest.mark.parametrize("preset", PRESET_NAMES)
def test_allocated_blocks_stay_inside_root_and_do_not_overlap(preset):
    analysis = analyze(load_preset(preset))
    root = ipaddress.ip_network(analysis.selected.vlsm.root)
    networks = [ipaddress.ip_network(block.cidr) for block in analysis.selected.vlsm.blocks]
    for network in networks:
        assert network.subnet_of(root)
    for index, first in enumerate(networks):
        for second in networks[index + 1 :]:
            assert not first.overlaps(second)


def test_campus_decision_categories_cover_the_rubric():
    analysis = analyze(load_preset("campus"))
    categories = {decision.category for decision in analysis.selected.decisions}
    assert "Physical media (L1)" in categories
    assert "Addressing (VLSM)" in categories
    assert "Topology" in categories
    assert "Routing (L3)" in categories
    assert "Switching (L2)" in categories
    assert "Security and hardening" in categories


def test_campus_alternate_collapsed_core_is_a_violation():
    analysis = analyze(load_preset("campus"))
    assert analysis.selected.topology.tier == "Three-tier"
    assert analysis.alternate.topology.tier == "Collapsed core"
    assert analysis.alternate.violations


def test_analysis_json_is_serializable():
    import json

    analysis = analyze(load_preset("metro"))
    payload = analysis.to_dict(include_configs=False)
    rendered = json.dumps(payload)
    assert '"selected"' in rendered
    assert '"alternate"' in rendered
