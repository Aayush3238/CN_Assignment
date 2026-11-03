"""Generated Cisco IOS configuration tests."""

from netarchitect.core.engine import run_scenario
from netarchitect.core.presets import PRESETS


def test_campus_switch_config_hardening():
    result = run_scenario(PRESETS["campus-lan"])
    switches = result.configs["switches.cfg"]

    assert "switchport trunk allowed vlan" in switches
    assert "switchport trunk allowed vlan all" not in switches
    assert "switchport trunk native vlan 999" in switches
    assert "spanning-tree mode rapid-pvst" in switches
    assert "spanning-tree portfast" in switches
    assert "spanning-tree bpduguard enable" in switches
    assert "ip access-group GUEST_ISOLATION in" in switches

    # Every user VLAN must appear in the explicit allowed list.
    for vlan in result.vlans:
        assert str(vlan.vlan_id) in switches
    assert "999" in switches


def test_router_config_uses_vlsm_gateways_and_ospf():
    result = run_scenario(PRESETS["campus-lan"])
    router = result.configs["router.cfg"]

    assert "router ospf 1" in router
    assert " passive-interface default" in router
    for vlan in result.vlans:
        assert f"interface GigabitEthernet0/0.{vlan.vlan_id}" in router
        assert f"encapsulation dot1Q {vlan.vlan_id}" in router
        assert f"ip address {vlan.gateway} " in router


def test_campus_router_has_no_wan_interface():
    result = run_scenario(PRESETS["campus-lan"])
    assert "interface GigabitEthernet0/1" not in result.configs["router.cfg"]


def test_metro_router_has_wan_interface():
    result = run_scenario(PRESETS["metro-man"])
    assert "interface GigabitEthernet0/1" in result.configs["router.cfg"]


def test_metro_generates_qos_but_not_vpn():
    result = run_scenario(PRESETS["metro-man"])
    assert "qos.cfg" in result.configs
    assert "priority percent 30" in result.configs["qos.cfg"]
    assert "vpn.cfg" not in result.configs


def test_global_generates_ipsec_and_bgp():
    result = run_scenario(PRESETS["global-wan"])
    assert "vpn.cfg" in result.configs
    assert "crypto isakmp policy 10" in result.configs["vpn.cfg"]
    assert "crypto map NETARCH-MAP" in result.configs["vpn.cfg"]
    assert "router bgp 65000" in result.configs["router.cfg"]
    assert "address-family ipv4 unicast" in result.configs["router.cfg"]


def test_guest_acl_blocks_internal_space():
    result = run_scenario(PRESETS["campus-lan"])
    acl = result.configs["acl.cfg"]
    assert "ip access-list extended GUEST_ISOLATION" in acl
    assert "deny ip any 10.0.0.0 0.255.255.255" in acl
    assert "permit tcp any any eq 443" in acl


def test_configs_use_no_real_secrets():
    for name in PRESETS:
        result = run_scenario(PRESETS[name])
        for content in result.configs.values():
            lowered = content.lower()
            assert "password" not in lowered
            assert "pre-shared-key" not in lowered
            assert "crypto isakmp key" not in lowered
