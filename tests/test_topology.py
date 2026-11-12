from __future__ import annotations

from netarchitect.core.design import design
from netarchitect.core.spec import load_preset
from tests.helpers import make_scenario


def test_preset_tiers():
    assert design(load_preset("campus")).topology.tier == "Three-tier"
    assert design(load_preset("metro")).topology.tier == "Collapsed core"
    assert design(load_preset("wan")).topology.tier == "Three-tier"


def test_campus_oversubscription_is_2_4_to_1():
    plan = design(load_preset("campus"))
    assert plan.topology.ratio == "2.4:1"
    assert plan.topology.oversubscription == 2.4


def test_access_switches_round_up():
    scenario = make_scenario(endpoints=100, subnets=[{"name": "U", "hosts": 90, "vlan": 10, "site": "Site"}])
    plan = design(scenario)
    assert plan.topology.access_switches == 3  # ceil(100 / 48)


def test_three_tier_threshold_on_endpoints():
    scenario = make_scenario(
        endpoints=1000,
        root_prefix="10.0.0.0/16",
        subnets=[{"name": "U", "hosts": 900, "vlan": 10, "site": "Site"}],
    )
    assert design(scenario).topology.tier == "Three-tier"


def test_collapsed_below_threshold():
    scenario = make_scenario(
        endpoints=999,
        root_prefix="10.0.0.0/16",
        subnets=[{"name": "U", "hosts": 900, "vlan": 10, "site": "Site"}],
    )
    assert design(scenario).topology.tier == "Collapsed core"


def test_three_tier_threshold_on_buildings():
    scenario = make_scenario(buildings=4)
    assert design(scenario).topology.tier == "Three-tier"


def test_forced_collapsed_core_is_a_violation():
    scenario = make_scenario(
        endpoints=1600,
        buildings=3,
        root_prefix="10.0.0.0/16",
        subnets=[{"name": "U", "hosts": 1500, "vlan": 10, "site": "Site"}],
        forced_tier="collapsed-core",
    )
    plan = design(scenario)
    assert plan.topology.tier == "Collapsed core"
    assert plan.topology.violation
    assert "violates the tier rule" in plan.topology.violation


def test_cost_is_not_scored_without_prices():
    plan = design(load_preset("campus"))
    assert plan.topology.cost is None
    assert "not scored" in plan.topology.cost_note


def test_cost_is_scored_with_prices():
    scenario = make_scenario(prices={"access": 1000, "distribution": 2000, "core": 5000})
    plan = design(scenario)
    expected = (
        plan.topology.access_switches * 1000
        + plan.topology.distribution_switches * 2000
        + plan.topology.core_switches * 5000
    )
    assert plan.topology.cost == expected
