from __future__ import annotations

import pytest

from netarchitect.core.design import design
from netarchitect.core.errors import InvalidParameterError
from netarchitect.core.spec import load_preset
from tests.helpers import make_scenario, scenario_dict
from dataclasses import replace


def test_campus_is_single_area_ospf():
    plan = design(load_preset("campus"))
    assert plan.routing.protocol == "OSPF Area 0"
    assert not plan.routing.multi_area
    assert not plan.routing.bgp
    assert all(network.area == 0 for network in plan.routing.networks)


def test_metro_is_multi_area_with_summaries():
    plan = design(load_preset("metro"))
    assert plan.routing.protocol == "Multi-area OSPF"
    assert plan.routing.multi_area
    assert not plan.routing.bgp
    assert plan.routing.summaries
    assert {summary.site for summary in plan.routing.summaries} == {"RemoteA", "RemoteB"}
    assert all(not summary.exact for summary in plan.routing.summaries)


def test_wan_adds_ebgp_and_ipsec():
    plan = design(load_preset("wan"))
    assert plan.routing.protocol == "Multi-area OSPF + eBGP"
    assert plan.routing.bgp
    assert plan.routing.local_asn == 65010
    assert plan.routing.peer_asn == 64512
    assert plan.routing.violation is None


def test_cloud_without_asns_is_rejected():
    scenario = load_preset("wan")
    broken = replace(scenario, local_asn=None)
    with pytest.raises(InvalidParameterError, match="local_asn and peer_asn"):
        design(broken)


def test_fifty_subnets_forces_multi_area():
    subnets = [
        {"name": f"S{index}", "hosts": 1, "vlan": index + 10, "site": "Site"}
        for index in range(50)
    ]
    scenario = make_scenario(
        endpoints=100,
        root_prefix="10.0.0.0/16",
        subnets=subnets,
        sites=[{"name": "Site", "subnets": [item["name"] for item in subnets], "role": "hq"}],
    )
    plan = design(scenario)
    assert plan.routing.multi_area
    assert plan.routing.protocol == "Multi-area OSPF"


def test_ospf_network_statements_use_wildcards_not_masks():
    plan = design(load_preset("campus"))
    for network in plan.routing.networks:
        assert network.wildcard != network.mask
        assert network.wildcard == "0.0.0.0" or network.wildcard.count(".") == 3


def test_area_assignments_for_metro():
    plan = design(load_preset("metro"))
    assert plan.routing.area_for_site["HQ"] == 0
    assert plan.routing.area_for_site["RemoteA"] == 1
    assert plan.routing.area_for_site["RemoteB"] == 2


def test_wan_summary_does_not_cover_cloud():
    plan = design(load_preset("wan"))
    cloud = plan.vlsm.by_name("Cloud-VPC")
    assert cloud is not None
    for summary in plan.routing.summaries:
        assert summary.cidr != cloud.cidr


def test_forced_single_area_on_multi_site_is_a_violation():
    plan = design(load_preset("metro"), routing_mode="area0")
    assert plan.routing.violation
    assert "multi-site" in plan.routing.violation


def test_forced_bgp_without_cloud_is_a_violation():
    plan = design(load_preset("campus"), routing_mode="bgp")
    assert plan.routing.bgp
    assert plan.routing.violation
