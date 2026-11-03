"""Cisco IOS configuration generator.

The output is intentionally conservative and copy-paste friendly:
* explicit trunk allowed lists (never ``switchport trunk allowed vlan all``)
* unused native VLAN 999
* PortFast/BPDU Guard on access ports
* router-on-a-stick SVIs matching the VLSM gateways
* OSPF areas/summaries derived from the routing decision
* a guest-isolation ACL, optional WAN QoS, and optional IPsec skeleton

Generated files use documentation addresses and placeholders where real
credentials or peer addresses would be required. Never commit real secrets.
"""

from __future__ import annotations

import ipaddress
import re

from netarchitect.core.models import (
    MediaRecommendation,
    RoutingDecision,
    ScenarioInput,
    Subnet,
    VLANPlan,
)


def _slug(text: str) -> str:
    """Turn a profile/name into a safe hostname fragment."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "netarch"


def _ios_vlan_name(text: str) -> str:
    """Cisco VLAN names cannot contain spaces and are limited to 32 chars."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_").upper()
    return (cleaned or "VLAN")[:32]


def _is_guest(name: str) -> bool:
    return "guest" in name.lower()


def _root_network(scenario: ScenarioInput) -> ipaddress.IPv4Network:
    return ipaddress.ip_network(scenario.root_prefix, strict=False)


def _switches_config(
    scenario: ScenarioInput,
    vlans: list[VLANPlan],
) -> str:
    """Build the L2 switch configuration."""
    slug = _slug(scenario.profile)
    root_id = next(
        (vlan.vlan_id for vlan in vlans if vlan.rstp_role.startswith("root")),
        vlans[0].vlan_id,
    )

    lines: list[str] = [
        "! NetArchitect generated switch configuration",
        f"! Profile: {scenario.profile}",
        "! Review interface names, port counts, and PoE budgets before applying.",
        "!",
        f"hostname {slug}-sw1",
        "!",
        "ip routing",
        "!",
        "! --- VLAN database ---",
    ]

    for vlan in vlans:
        lines.extend([f"vlan {vlan.vlan_id}", f" name {_ios_vlan_name(vlan.name)}", "!"])

    # Native VLAN is created but never assigned to user traffic.
    lines.extend(["vlan 999", " name NATIVE_UNUSED", "!", "! --- Spanning tree ---"])
    lines.append("spanning-tree mode rapid-pvst")
    lines.append(f"spanning-tree vlan {root_id} priority 4096")
    lines.append("!")

    if scenario.resiliency != "single-homed":
        lines.append(
            f"! Resiliency: {scenario.resiliency}. Deploy paired distribution "
            "switches and an HSRP/VRRP gateway peer."
        )
        lines.append("!")

    # SVIs: one per VLAN, using the exact gateway allocated by the VLSM engine.
    lines.append("! --- VLAN gateways (SVIs) ---")
    for vlan in vlans:
        if not vlan.subnet or not vlan.gateway:
            continue
        network = ipaddress.ip_network(vlan.subnet)
        lines.extend(
            [
                f"interface Vlan{vlan.vlan_id}",
                f" description {vlan.name} gateway",
                f" ip address {vlan.gateway} {network.netmask}",
            ]
        )
        if _is_guest(vlan.name):
            lines.append(" ip access-group GUEST_ISOLATION in")
        lines.extend([" no shutdown", "!"])

    # Trunk with an explicit allowed list and an unused native VLAN.
    allowed = ",".join(str(vlan_id) for vlan_id in vlans[0].trunk_allowed)
    lines.extend(
        [
            "! --- Uplink trunk (explicit allowed VLANs) ---",
            "interface GigabitEthernet0/1",
            " description Uplink trunk to distribution/core",
            " switchport trunk encapsulation dot1q",
            " switchport mode trunk",
            " switchport trunk native vlan 999",
            f" switchport trunk allowed vlan {allowed}",
            " switchport nonegotiate",
            " no shutdown",
            "!",
            "! --- Access ports (sample; expand to match endpoint count) ---",
        ]
    )

    port_index = 1
    for vlan in vlans:
        # Keep output readable while proving access-port config for each VLAN.
        for _ in range(2):
            if port_index > 12:
                break
            lines.extend(
                [
                    f"interface GigabitEthernet1/0/{port_index}",
                    f" description Access - {vlan.name}",
                    " switchport mode access",
                    f" switchport access vlan {vlan.vlan_id}",
                    " spanning-tree portfast",
                    " spanning-tree bpduguard enable",
                ]
            )
            if vlan.poe:
                lines.append(" power inline auto")
            lines.append("!")
            port_index += 1

    lines.extend(["end", ""])
    return "\n".join(lines)


def _area_for(cidr: str, routing: RoutingDecision) -> str:
    for area, cidrs in routing.areas.items():
        if cidr in cidrs:
            return area
    return "0"


def _router_config(
    scenario: ScenarioInput,
    media: list[MediaRecommendation],
    subnets: list[Subnet],
    vlans: list[VLANPlan],
    routing: RoutingDecision,
) -> str:
    """Build the L3 router configuration (router-on-a-stick + WAN)."""
    slug = _slug(scenario.profile)
    root = _root_network(scenario)
    router_id = str(ipaddress.IPv4Address(int(root.network_address) + 1))

    lines: list[str] = [
        "! NetArchitect generated router configuration",
        f"! Profile: {scenario.profile}",
        "!",
        f"hostname {slug}-rtr",
        "!",
        "! --- LAN trunk and VLAN subinterfaces ---",
        "interface GigabitEthernet0/0",
        " description LAN trunk to L3 switch",
        " no ip address",
        " no shutdown",
        "!",
    ]

    for vlan in vlans:
        if not vlan.subnet or not vlan.gateway:
            continue
        network = ipaddress.ip_network(vlan.subnet)
        lines.extend(
            [
                f"interface GigabitEthernet0/0.{vlan.vlan_id}",
                f" description {vlan.name} gateway",
                f" encapsulation dot1Q {vlan.vlan_id}",
                f" ip address {vlan.gateway} {network.netmask}",
                " no shutdown",
                "!",
            ]
        )

    # WAN interface: only emit it when the scenario actually has a WAN link.
    has_wan = scenario.wan_distance_m > 0 or scenario.cloud_vpc
    wan_media = next((item for item in media if item.category == "wan"), None)
    if has_wan:
        lines.append("! --- WAN uplink ---")
        lines.append("interface GigabitEthernet0/1")
        if wan_media:
            lines.append(
                f" description WAN ({wan_media.media}, {wan_media.transceiver})"
            )
        else:
            lines.append(" description WAN uplink")

        if scenario.wan_service == "internet" or scenario.cloud_vpc:
            lines.extend(
                [
                    " ip address dhcp",
                    " no shutdown",
                    "!",
                    "! Default route points at the ISP handoff (replace with real next hop).",
                    "ip route 0.0.0.0 0.0.0.0 192.0.2.1",
                ]
            )
        else:
            lines.extend(
                [
                    "! Replace the documentation /30 with the carrier-provided link.",
                    " ip address 192.0.2.1 255.255.255.252",
                    " no shutdown",
                ]
            )
        lines.append("!")

    # OSPF: advertise each subnet with its wildcard mask in the right area.
    lines.extend(
        [
            "! --- OSPF ---",
            "router ospf 1",
            f" router-id {router_id}",
            " passive-interface default",
            " no passive-interface GigabitEthernet0/0",
        ]
    )
    if has_wan:
        lines.append(" no passive-interface GigabitEthernet0/1")
    for subnet in subnets:
        area = _area_for(subnet.cidr, routing)
        lines.append(
            f" network {subnet.network} {subnet.wildcard} area {area}"
        )
    for summary in routing.summarization:
        lines.append(f" {summary}")

    # eBGP is only relevant when the design crosses into a cloud VPC.
    if scenario.cloud_vpc:
        lines.extend(
            [
                "!",
                "! --- eBGP to cloud VPC (placeholder ASN/peer) ---",
                "router bgp 65000",
                f" bgp router-id {router_id}",
                " bgp log-neighbor-changes",
                " neighbor 192.0.2.2 remote-as 64512",
                " !",
                " address-family ipv4 unicast",
            ]
        )
        for subnet in subnets:
            lines.append(
                f"  network {subnet.network} mask {subnet.netmask}"
            )
        lines.extend(
            [
                "  neighbor 192.0.2.2 activate",
                "  neighbor 192.0.2.2 route-map FROM-CLOUD in",
                " exit-address-family",
                "!",
                "route-map FROM-CLOUD permit 10",
                " set local-preference 200",
            ]
        )

    lines.extend(["!", "end", ""])
    return "\n".join(lines)


def _acl_config(scenario: ScenarioInput, vlans: list[VLANPlan]) -> str:
    """Build a guest-isolation ACL.

    Guest VLANs may reach the internet but must not reach internal address
    space. The ACL is applied inbound on guest SVIs in the switch config.
    """
    guest_vlans = [vlan for vlan in vlans if _is_guest(vlan.name)]
    if not guest_vlans:
        return (
            "! NetArchitect: no guest VLAN detected, so no isolation ACL was generated.\n"
        )

    root = _root_network(scenario)
    return "\n".join(
        [
            "! NetArchitect generated guest isolation ACL",
            "! Applied inbound on guest SVIs (see switches.cfg).",
            "ip access-list extended GUEST_ISOLATION",
            " remark Block guest VLANs from internal address space",
            f" deny ip any {root.network_address} {root.hostmask}",
            " deny ip any 10.0.0.0 0.255.255.255",
            " deny ip any 172.16.0.0 0.15.255.255",
            " deny ip any 192.168.0.0 0.0.255.255",
            " permit udp any any eq 53",
            " permit tcp any any eq 443",
            " permit ip any any",
            "!",
            "end",
            "",
        ]
    )


def _qos_config(scenario: ScenarioInput) -> str | None:
    """Build a WAN QoS policy when the scenario specifies a latency target."""
    if scenario.qos_latency_ms is None:
        return None
    return "\n".join(
        [
            "! NetArchitect generated WAN QoS policy",
            f"! Target application latency: {scenario.qos_latency_ms:g} ms",
            "! Apply after router.cfg; the interface already exists there.",
            "class-map match-any VOICE",
            " match dscp ef",
            "class-map match-any SIGNALLING",
            " match dscp cs3",
            "!",
            "policy-map WAN-QOS",
            " class VOICE",
            "  priority percent 30",
            " class SIGNALLING",
            "  bandwidth percent 10",
            " class class-default",
            "  fair-queue",
            "  random-detect",
            "!",
            "interface GigabitEthernet0/1",
            " service-policy output WAN-QOS",
            "!",
            "end",
            "",
        ]
    )


def _vpn_config(scenario: ScenarioInput) -> str | None:
    """Build an IPsec skeleton for cloud/internet WAN designs."""
    if not (
        scenario.cloud_vpc
        or (scenario.wan_service == "internet" and scenario.wan_distance_m > 0)
    ):
        return None

    root = _root_network(scenario)
    return "\n".join(
        [
            "! NetArchitect generated IPsec VPN skeleton",
            "! Replace peer addresses and ASNs with the contracted values.",
            "! Never commit the pre-shared key; configure it out-of-band.",
            "crypto isakmp policy 10",
            " encr aes 256",
            " hash sha256",
            " authentication pre-share",
            " group 14",
            " lifetime 28800",
            "!",
            "crypto ipsec transform-set NETARCH-TS esp-aes 256 esp-sha256-hmac",
            " mode tunnel",
            "!",
            "ip access-list extended VPN-INTERESTING",
            f" permit ip {root.network_address} {root.hostmask} 172.31.0.0 0.0.255.255",
            "!",
            "crypto map NETARCH-MAP 10 ipsec-isakmp",
            " set peer 198.51.100.2",
            " set transform-set NETARCH-TS",
            " match address VPN-INTERESTING",
            "!",
            "interface GigabitEthernet0/1",
            " crypto map NETARCH-MAP",
            "!",
            "end",
            "",
        ]
    )


def build_configs(
    scenario: ScenarioInput,
    media: list[MediaRecommendation],
    subnets: list[Subnet],
    vlans: list[VLANPlan],
    routing: RoutingDecision,
) -> dict[str, str]:
    """Return a filename -> IOS configuration mapping for the run."""
    configs = {
        "switches.cfg": _switches_config(scenario, vlans),
        "router.cfg": _router_config(scenario, media, subnets, vlans, routing),
        "acl.cfg": _acl_config(scenario, vlans),
    }

    qos = _qos_config(scenario)
    if qos:
        configs["qos.cfg"] = qos

    vpn = _vpn_config(scenario)
    if vpn:
        configs["vpn.cfg"] = vpn

    return configs
