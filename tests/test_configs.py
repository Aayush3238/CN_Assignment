from __future__ import annotations

import pytest

from netarchitect.configs.configs import build_configs, build_devices
from netarchitect.core.design import analyze
from netarchitect.core.spec import load_preset


def campus():
    return analyze(load_preset("campus"))


def metro():
    return analyze(load_preset("metro"))


def wan():
    return analyze(load_preset("wan"))


def test_campus_has_cores_distribution_and_access():
    devices = build_devices(campus().selected)
    names = [device.hostname for device in devices]
    assert names[:2] == ["campus-core1", "campus-core2"]
    assert "campus-dist1" in names
    assert "campus-acc1" in names


def test_campus_config_has_no_wan_or_bgp():
    analysis = campus()
    joined = "\n".join(analysis.device_configs.values())
    assert "router bgp" not in joined
    assert "crypto map" not in joined
    assert "WAN link" not in joined


def test_trunks_have_explicit_sorted_allowed_vlans_and_native_999():
    analysis = campus()
    joined = "\n".join(analysis.device_configs.values())
    assert "switchport trunk allowed vlan 10,20,30,40,50" in joined
    assert "switchport trunk native vlan 999" in joined
    assert "allowed vlan all" not in joined
    assert "\nvlan 999\n" not in joined


def test_access_ports_have_portfast_and_bpdu_guard():
    analysis = campus()
    for hostname, config in analysis.device_configs.items():
        if "-acc" in hostname:
            assert "spanning-tree portfast" in config
            assert "spanning-tree bpduguard enable" in config
            assert "power inline auto" in config


def test_campus_core1_and_core2_have_unique_router_ids_and_hsrp_priorities():
    analysis = campus()
    core1 = analysis.device_configs["campus-core1"]
    core2 = analysis.device_configs["campus-core2"]
    assert "router-id 10.10.8.2" in core1
    assert "router-id 10.10.8.3" in core2
    assert "standby 10 ip 10.10.0.1" in core1
    assert "standby 10 priority 110" in core1
    assert "standby 10 priority 100" in core2


def test_guest_acl_applied_to_wifi_svi():
    analysis = campus()
    core = analysis.device_configs["campus-core1"]
    assert "ip access-list extended GUEST-ISOLATION" in core
    assert "deny ip 10.10.4.0 0.0.1.255 10.10.8.128 0.0.0.127" in core
    assert "interface Vlan30\n ip access-group GUEST-ISOLATION in" in core


def test_metro_hq_has_qos_and_remote_routers_have_area_ranges():
    analysis = metro()
    hq = analysis.device_configs["metro-hq-rtr"]
    remote_a = analysis.device_configs["metro-remotea-rtr"]
    assert "policy-map WAN-QOS" in hq
    assert "service-policy output WAN-QOS" in hq
    assert "area 1 range 10.20.1.128 255.255.255.128" in remote_a
    assert "area 1 range" not in hq


def test_wan_has_bgp_and_ipsec_on_the_cloud_boundary():
    analysis = wan()
    hub = analysis.device_configs["wan-citya-rtr"]
    cloud = analysis.device_configs["wan-cloud-rtr"]
    assert "router bgp 65010" in hub
    assert "neighbor 10.64.11.14 remote-as 64512" in hub
    assert "crypto map WAN-MAP" in hub
    assert "match address VPN-TRAFFIC" in hub
    assert "router bgp 64512" in cloud
    assert "neighbor 10.64.11.13 remote-as 65010" in cloud


def test_every_config_ends_with_end_and_has_no_jinja_leakage():
    for analysis in (campus(), metro(), wan()):
        for hostname, config in analysis.device_configs.items():
            assert config.rstrip().endswith("end"), hostname
            assert "{{" not in config
            assert "Undefined" not in config


def test_combined_export_has_one_banner_per_device():
    analysis = wan()
    devices, text = build_configs(analysis.selected)
    assert text.count("! ===== DEVICE:") == len(devices)
    for hostname in devices:
        assert f"! ===== DEVICE: {hostname} =====" in text


@pytest.mark.parametrize("preset", ["campus", "metro", "wan"])
def test_all_presets_render(preset):
    analysis = analyze(load_preset(preset))
    assert analysis.device_configs
    assert analysis.export_text.startswith("! NetArchitect export")
