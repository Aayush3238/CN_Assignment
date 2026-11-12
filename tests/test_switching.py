from __future__ import annotations

from netarchitect.core.design import design
from netarchitect.core.spec import load_preset
from tests.helpers import make_scenario


def test_campus_uses_rstp_and_hsrp():
    plan = design(load_preset("campus"))
    assert plan.switching.stp == "RSTP"
    assert plan.switching.stp_mode == "rapid-pvst"
    assert plan.switching.fhrp == "HSRP"


def test_non_resilient_has_no_fhrp():
    scenario = make_scenario(resilient=False)
    plan = design(scenario)
    assert plan.switching.fhrp == "None"
    assert "VRRP" in plan.switching.reason


def test_more_than_sixteen_vlans_forces_mstp():
    subnets = [
        {"name": f"V{index}", "hosts": 1, "vlan": index + 10, "site": "Site"}
        for index in range(20)
    ]
    scenario = make_scenario(
        endpoints=40,
        root_prefix="10.0.0.0/16",
        subnets=subnets,
        sites=[{"name": "Site", "subnets": [item["name"] for item in subnets]}],
    )
    plan = design(scenario)
    assert plan.switching.vlan_count == 20
    assert plan.switching.stp == "MSTP"
    assert plan.switching.stp_mode == "mst"


def test_native_vlan_is_not_in_allowed_list():
    plan = design(load_preset("campus"))
    assert plan.switching.native_vlan == 999
    assert 999 not in plan.switching.allowed_vlans
    assert plan.switching.allowed_vlans == (10, 20, 30, 40, 50)


def test_hardening_rules_are_recorded():
    plan = design(load_preset("campus"))
    joined = " ".join(plan.switching.hardening)
    assert "allowed vlan all" in joined  # the rule says it is never emitted
    assert "Native VLAN" in joined
