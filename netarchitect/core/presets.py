"""The three preset scenarios required by the assignment specification.

Each preset is a plain :class:`ScenarioInput`, so presets and user-supplied JSON
flow through exactly the same validation and rule engine.
"""

from __future__ import annotations

from netarchitect.core.models import ScenarioInput, VLANRequest

CAMPUS_LAN = ScenarioInput(
    profile="campus-lan",
    description=(
        "Campus LAN: 3 buildings within 400 m, 1,600 endpoints and PoE access "
        "points. Focus: Cat6a/MMF, 802.1Q VLANs, RSTP, single-area OSPF."
    ),
    buildings=3,
    endpoints=1600,
    access_distance_m=90,
    backbone_distance_m=350,
    wan_distance_m=0,
    uplink_gbps=10,
    poe_aps=60,
    resiliency="dual-uplink",
    cloud_vpc=False,
    root_prefix="10.0.0.0/16",
    vlans=[
        VLANRequest(name="Staff", hosts=400, purpose="Employee wired/wireless", vlan_id=10),
        VLANRequest(name="Students", hosts=700, purpose="Student devices", vlan_id=20),
        VLANRequest(name="Voice", hosts=250, purpose="VoIP handsets", poe=True, vlan_id=30),
        VLANRequest(name="Guest", hosts=100, purpose="Untrusted guest Wi-Fi", vlan_id=40),
        VLANRequest(name="IoT", hosts=50, purpose="Building sensors", vlan_id=50),
        VLANRequest(name="Management", hosts=20, purpose="Infrastructure management", vlan_id=60),
    ],
)

METRO_MAN = ScenarioInput(
    profile="metro-man",
    description=(
        "Metro MAN: HQ plus two remote sites (15-35 km), 450 users and a FinTech "
        "colo. Focus: OS2 SMF, EVPL, sub-5 ms QoS, dual-homed failover."
    ),
    buildings=1,
    remote_sites=2,
    endpoints=450,
    access_distance_m=90,
    backbone_distance_m=300,
    wan_distance_m=22000,
    wan_service="dark-fiber",
    uplink_gbps=10,
    poe_aps=20,
    resiliency="dual-homed",
    cloud_vpc=False,
    qos_latency_ms=5,
    root_prefix="10.10.0.0/16",
    vlans=[
        VLANRequest(name="Corporate", hosts=200, purpose="HQ corporate users", vlan_id=10),
        VLANRequest(name="Trading", hosts=120, purpose="Low-latency trading floor", vlan_id=20),
        VLANRequest(name="Voice", hosts=50, purpose="Trading turret/voice", poe=True, vlan_id=30),
        VLANRequest(name="Guest", hosts=40, purpose="Visitor access", vlan_id=40),
        VLANRequest(name="Management", hosts=18, purpose="Out-of-band management", vlan_id=50),
        VLANRequest(name="Colo-DMZ", hosts=20, purpose="FinTech colocation services", vlan_id=60),
    ],
)

GLOBAL_WAN = ScenarioInput(
    profile="global-wan",
    description=(
        "Global WAN: four cities plus a cloud VPC, 2,000 IoT/scanner devices. "
        "Focus: IPsec VPN, multi-area OSPF/BGP, route summarization."
    ),
    buildings=0,
    remote_sites=4,
    endpoints=2000,
    access_distance_m=90,
    backbone_distance_m=0,
    wan_distance_m=5_000_000,
    wan_service="internet",
    uplink_gbps=10,
    poe_aps=30,
    resiliency="dual-homed",
    cloud_vpc=True,
    qos_latency_ms=150,
    root_prefix="10.20.0.0/16",
    vlans=[
        VLANRequest(name="IoT", hosts=1200, purpose="Warehouse sensors", vlan_id=10),
        VLANRequest(name="Scanners", hosts=500, purpose="Handheld scanners", vlan_id=20),
        VLANRequest(name="Corporate", hosts=200, purpose="City office users", vlan_id=30),
        VLANRequest(name="Management", hosts=80, purpose="Infrastructure management", vlan_id=40),
        VLANRequest(name="Guest", hosts=20, purpose="Visitor access", vlan_id=50),
    ],
)

PRESETS: dict[str, ScenarioInput] = {
    "campus-lan": CAMPUS_LAN,
    "metro-man": METRO_MAN,
    "global-wan": GLOBAL_WAN,
}

# Friendly aliases reduce friction at the terminal.
_ALIASES = {
    "campus": "campus-lan",
    "lan": "campus-lan",
    "metro": "metro-man",
    "man": "metro-man",
    "global": "global-wan",
    "wan": "global-wan",
}


def preset_names() -> list[str]:
    """Return preset identifiers in a stable, user-facing order."""
    return list(PRESETS)


def get_preset(name: str) -> ScenarioInput:
    """Look up a preset by canonical name or alias.

    The returned model is deep-copied so callers can safely mutate it (for
    example when tweaking a preset) without corrupting the module-level object.
    """
    key = name.strip().lower().replace("_", "-")
    key = _ALIASES.get(key, key)
    if key not in PRESETS:
        choices = ", ".join(PRESETS)
        raise KeyError(f"unknown preset '{name}'. Available presets: {choices}")
    return PRESETS[key].model_copy(deep=True)
