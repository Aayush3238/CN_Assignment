"""End-to-end engine tests for the three required presets."""

import pytest

from netarchitect.core.engine import run_scenario
from netarchitect.core.presets import PRESETS


@pytest.mark.parametrize("name", list(PRESETS))
def test_every_preset_produces_a_complete_result(name):
    result = run_scenario(PRESETS[name])

    assert result.scenario.profile == name
    assert len(result.subnets) == len(result.scenario.vlans)
    assert len(result.vlans) == len(result.scenario.vlans)
    assert result.media
    assert result.configs
    assert result.rationales
    assert result.utilization.address_pct > 0
    assert result.utilization.host_pct > 0

    # Every rationale record must be fully populated for the audit trail.
    for entry in result.rationales:
        assert entry.rule_id
        assert entry.domain
        assert entry.condition
        assert entry.choice
        assert entry.rationale


def test_campus_media_and_routing_choices():
    result = run_scenario(PRESETS["campus-lan"])
    media_by_link = {item.link: item for item in result.media}
    assert media_by_link["LAN access"].transceiver == "10GBASE-T"
    assert media_by_link["Building/site backbone"].transceiver == "10GBASE-SR"
    assert result.routing.rule_id == "L3-ROUTE-01"


def test_metro_wan_uses_single_mode_er():
    result = run_scenario(PRESETS["metro-man"])
    wan = next(item for item in result.media if item.category == "wan")
    assert wan.transceiver == "10GBASE-ER"
    assert wan.media == "OS2 single-mode fiber"


def test_global_wan_is_carrier_ipsec():
    result = run_scenario(PRESETS["global-wan"])
    wan = next(item for item in result.media if item.category == "wan")
    assert "IPsec" in wan.media
    assert result.routing.rule_id == "L3-ROUTE-03"


def test_gateways_match_allocated_subnets():
    result = run_scenario(PRESETS["campus-lan"])
    subnets = {subnet.name: subnet for subnet in result.subnets}
    for vlan in result.vlans:
        assert vlan.subnet == subnets[vlan.name].cidr
        assert vlan.gateway == subnets[vlan.name].gateway
