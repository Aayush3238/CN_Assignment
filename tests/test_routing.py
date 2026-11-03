"""L3 routing protocol selection tests."""

from netarchitect.core.models import ScenarioInput, VLANRequest
from netarchitect.core.presets import CAMPUS_LAN, GLOBAL_WAN, METRO_MAN
from netarchitect.core.routing import decide_routing
from netarchitect.core.vlsm import VLSMRequest, allocate_vlsm


def _subnets(scenario: ScenarioInput):
    requests = [VLSMRequest(vlan.name, vlan.hosts) for vlan in scenario.vlans]
    return allocate_vlsm(scenario.root_prefix, requests).subnets


def _scenario_with_vlan_count(count: int) -> ScenarioInput:
    return ScenarioInput(
        profile="routing-threshold",
        endpoints=count,
        root_prefix="10.0.0.0/16",
        vlans=[VLANRequest(name=f"V{index}", hosts=1) for index in range(count)],
    )


def test_campus_uses_single_area_ospf():
    decision = decide_routing(CAMPUS_LAN, _subnets(CAMPUS_LAN))
    assert decision.rule_id == "L3-ROUTE-01"
    assert decision.protocol == "OSPF Area 0 (single area)"
    assert set(decision.areas) == {"0"}


def test_metro_uses_multi_area_ospf():
    decision = decide_routing(METRO_MAN, _subnets(METRO_MAN))
    assert decision.rule_id == "L3-ROUTE-02"
    assert "Multi-Area OSPF" in decision.protocol
    assert len(decision.areas) > 1


def test_global_uses_ebgp_at_cloud_boundary():
    decision = decide_routing(GLOBAL_WAN, _subnets(GLOBAL_WAN))
    assert decision.rule_id == "L3-ROUTE-03"
    assert "eBGP" in decision.protocol


def test_fifty_subnets_trigger_multi_area():
    scenario = _scenario_with_vlan_count(50)
    decision = decide_routing(scenario, _subnets(scenario))
    assert decision.rule_id == "L3-ROUTE-02"


def test_forty_nine_subnets_stay_single_area():
    scenario = _scenario_with_vlan_count(49)
    decision = decide_routing(scenario, _subnets(scenario))
    assert decision.rule_id == "L3-ROUTE-01"


def test_remote_site_triggers_multi_area_even_when_small():
    scenario = ScenarioInput(
        profile="small-remote",
        endpoints=20,
        remote_sites=1,
        root_prefix="10.0.0.0/24",
        vlans=[
            VLANRequest(name="Staff", hosts=10),
            VLANRequest(name="Management", hosts=5),
        ],
    )
    decision = decide_routing(scenario, _subnets(scenario))
    assert decision.rule_id == "L3-ROUTE-02"


def test_summarisation_commands_are_cisco_syntax():
    decision = decide_routing(METRO_MAN, _subnets(METRO_MAN))
    for command in decision.summarization:
        assert command.startswith("area ")
        assert " range " in command
