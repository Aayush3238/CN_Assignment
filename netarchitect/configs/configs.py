"""Cisco IOS configuration generation.

One Jinja2 template is rendered once per device.  The devices are built from
the *plan objects* (the already-computed subnets, areas, HSRP addresses and
hardening choices), not from the raw scenario, so the CLI, the dashboard, and
the tests all see the same numbers.

The export is a single text file per preset, split by a banner:

    ! ===== DEVICE: campus-core1 =====

The Packet Tracer instructions in the README explain how to paste each block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from netarchitect.core.ipv4 import format_ipv4
from netarchitect.core.spec import Scenario
from netarchitect.core.vlsm import SubnetBlock

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
LAB_SECRET = "NetArchitect-Lab-123"
IPSEC_KEY = "NetArchitect-Lab-Key"
SERIAL_NAMES = ("Serial0/0/0", "Serial0/1/0", "Serial0/2/0", "Serial0/3/0")


@dataclass
class VlanDef:
    id: int
    name: str


@dataclass
class HsrpDef:
    group: int
    virtual: str
    priority: int


@dataclass
class InterfaceDef:
    name: str
    description: str = ""
    mode: str = "routed"  # trunk | access | svi | routed | physical | loopback
    vlan: int | None = None
    ip: str | None = None
    mask: str | None = None
    allowed_vlans: list[int] = field(default_factory=list)
    native_vlan: int | None = None
    poe: bool = False
    hsrp: HsrpDef | None = None
    clock_rate: int | None = None
    crypto_map: bool = False
    qos: bool = False


@dataclass
class OspfDef:
    process: int
    router_id: str
    networks: list[tuple[str, str, int]] = field(default_factory=list)
    passive: list[str] = field(default_factory=list)
    ranges: list[tuple[int, str, str]] = field(default_factory=list)


@dataclass
class BgpDef:
    local_asn: int
    neighbors: list[tuple[str, int]] = field(default_factory=list)
    networks: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class AclDef:
    name: str
    lines: list[str] = field(default_factory=list)
    interface: str | None = None


@dataclass
class IpsecDef:
    peer: str
    local_network: str
    local_wildcard: str
    remote_network: str
    remote_wildcard: str
    map_name: str
    key: str = IPSEC_KEY


@dataclass
class DeviceConfig:
    hostname: str
    role: str
    l3: bool = False
    vlans: list[VlanDef] = field(default_factory=list)
    interfaces: list[InterfaceDef] = field(default_factory=list)
    ospf: OspfDef | None = None
    bgp: BgpDef | None = None
    acls: list[AclDef] = field(default_factory=list)
    ipsec: IpsecDef | None = None
    qos: bool = False
    qos_network: str | None = None
    qos_wildcard: str | None = None
    stp_mode: str | None = None
    stp_priority_vlans: list[int] = field(default_factory=list)
    vty_acl: str | None = None
    default_gateway: str | None = None
    comment: str = ""


def _ip(block: SubnetBlock, offset: int) -> str:
    return format_ipv4(block.network_int + offset)


def _vlan_name(name: str) -> str:
    return name.upper().replace(" ", "-").replace("_", "-")[:32]


def _vlans(plan) -> list[VlanDef]:
    return sorted(
        (
            VlanDef(block.vlan, _vlan_name(block.name))
            for block in plan.vlsm.blocks
            if block.vlan is not None
        ),
        key=lambda vlan: vlan.id,
    )


def _allowed(plan) -> list[int]:
    return sorted(block.vlan for block in plan.vlsm.blocks if block.vlan is not None)


def _lan_blocks(plan) -> list[SubnetBlock]:
    return [block for block in plan.vlsm.blocks if not block.point_to_point]


def _find_block(plan, *needles: str) -> SubnetBlock | None:
    for block in plan.vlsm.blocks:
        name = block.name.lower().replace("_", "-")
        if all(needle.lower() in name for needle in needles):
            return block
    return None


def _mgmt(plan) -> SubnetBlock:
    block = _find_block(plan, "management") or _find_block(plan, "mgmt")
    if block is not None:
        return block
    return _lan_blocks(plan)[0]


def _hub_site(scenario: Scenario):
    for site in scenario.sites:
        if site.role in {"hq", "hub", "core"}:
            return site
    return scenario.sites[0]


def _site_block(plan, site_name: str) -> SubnetBlock | None:
    for block in _lan_blocks(plan):
        if (block.site or "").lower() == site_name.lower():
            return block
    return None


def _p2p(plan, first: str, second: str) -> SubnetBlock | None:
    wanted = {first.lower(), second.lower()}
    for block in plan.vlsm.blocks:
        if not block.between:
            continue
        if {name.lower() for name in block.between} == wanted:
            return block
    return None


def _mgmt_acl(plan) -> tuple[AclDef, str]:
    mgmt = _mgmt(plan)
    acl = AclDef(
        "MGMT-ACCESS",
        [
            f"permit tcp {mgmt.network} {mgmt.wildcard} any eq 22",
            "deny ip any any",
        ],
    )
    return acl, "MGMT-ACCESS"


def _ospf_networks(blocks) -> list[tuple[str, str, int]]:
    seen: set[tuple[str, str, int]] = set()
    result: list[tuple[str, str, int]] = []
    for block, area in blocks:
        item = (block.network, block.wildcard, area)
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _campus_devices(plan) -> list[DeviceConfig]:
    scenario = plan.scenario
    vlans = _vlans(plan)
    allowed = _allowed(plan)
    native = scenario.native_vlan
    mgmt = _mgmt(plan)
    mgmt_acl, mgmt_name = _mgmt_acl(plan)
    wifi = _find_block(plan, "wi-fi") or _find_block(plan, "wifi")
    servers = _find_block(plan, "server")
    voice = _find_block(plan, "voice")
    data = _find_block(plan, "data") or _lan_blocks(plan)[0]

    acls = [mgmt_acl]
    if wifi and servers:
        acls.append(
            AclDef(
                "GUEST-ISOLATION",
                [
                    f"deny ip {wifi.network} {wifi.wildcard} {servers.network} {servers.wildcard}",
                    "permit ip any any",
                ],
                interface=f"Vlan{wifi.vlan}",
            )
        )

    devices: list[DeviceConfig] = []
    core_count = 2 if scenario.resilient else 1
    for index in range(core_count):
        interfaces: list[InterfaceDef] = []
        for dist in range(1, scenario.buildings + 1):
            interfaces.append(
                InterfaceDef(
                    name=f"GigabitEthernet1/0/{dist}",
                    description=f"Trunk to distribution {dist}",
                    mode="trunk",
                    allowed_vlans=list(allowed),
                    native_vlan=native,
                )
            )
        networks: list[tuple[str, str, int]] = []
        passive: list[str] = []
        for block in _lan_blocks(plan):
            if block.vlan is None:
                continue
            if scenario.resilient:
                hsrp = HsrpDef(block.vlan, block.gateway, 110 if index == 0 else 100)
                address = _ip(block, 2 + index)
            else:
                hsrp = None
                address = block.gateway
            interfaces.append(
                InterfaceDef(
                    name=f"Vlan{block.vlan}",
                    description=block.name,
                    mode="svi",
                    vlan=block.vlan,
                    ip=address,
                    mask=block.mask,
                    hsrp=hsrp,
                )
            )
            area = plan.routing.area_for_site.get(block.site or "Core", 0)
            networks.append((block.network, block.wildcard, area))
            passive.append(f"Vlan{block.vlan}")
        devices.append(
            DeviceConfig(
                hostname=f"{scenario.name}-core{index + 1}",
                role="Layer-3 core switch",
                l3=True,
                vlans=list(vlans),
                interfaces=interfaces,
                ospf=OspfDef(
                    1,
                    _ip(mgmt, 2 + index) if scenario.resilient else mgmt.gateway,
                    networks,
                    passive,
                    [],
                ),
                acls=list(acls),
                stp_mode=plan.switching.stp_mode,
                stp_priority_vlans=list(allowed) if index == 0 else [],
                vty_acl=mgmt_name,
            )
        )

    for dist in range(1, scenario.buildings + 1):
        interfaces = [
            InterfaceDef(
                name=f"GigabitEthernet0/{core}",
                description=f"Trunk to core {core}",
                mode="trunk",
                allowed_vlans=list(allowed),
                native_vlan=native,
            )
            for core in range(1, core_count + 1)
        ]
        interfaces.append(
            InterfaceDef(
                name="GigabitEthernet0/3",
                description=f"Trunk to access switch {dist}",
                mode="trunk",
                allowed_vlans=list(allowed),
                native_vlan=native,
            )
        )
        interfaces.append(
            InterfaceDef(
                name=f"Vlan{mgmt.vlan or 40}",
                description="Management SVI",
                mode="svi",
                ip=_ip(mgmt, 20 + dist),
                mask=mgmt.mask,
            )
        )
        devices.append(
            DeviceConfig(
                hostname=f"{scenario.name}-dist{dist}",
                role="Layer-2 distribution switch",
                vlans=list(vlans),
                interfaces=interfaces,
                acls=[mgmt_acl],
                stp_mode=plan.switching.stp_mode,
                vty_acl=mgmt_name,
                default_gateway=mgmt.gateway,
            )
        )

    for access in range(1, scenario.buildings + 1):
        interfaces = [
            InterfaceDef(
                name="GigabitEthernet0/1",
                description=f"Trunk to distribution {access}",
                mode="trunk",
                allowed_vlans=list(allowed),
                native_vlan=native,
            )
        ]
        for port in range(1, 25):
            if voice is not None and port <= 6:
                vlan, poe = voice.vlan, True
            elif wifi is not None and port <= 12:
                vlan, poe = wifi.vlan, True
            else:
                vlan, poe = data.vlan, False
            interfaces.append(
                InterfaceDef(
                    name=f"FastEthernet0/{port}",
                    description=f"Access port {port}",
                    mode="access",
                    vlan=vlan,
                    poe=poe,
                )
            )
        interfaces.append(
            InterfaceDef(
                name=f"Vlan{mgmt.vlan or 40}",
                description="Management SVI",
                mode="svi",
                ip=_ip(mgmt, 40 + access),
                mask=mgmt.mask,
            )
        )
        devices.append(
            DeviceConfig(
                hostname=f"{scenario.name}-acc{access}",
                role="Layer-2 access switch",
                vlans=list(vlans),
                interfaces=interfaces,
                acls=[mgmt_acl],
                stp_mode=plan.switching.stp_mode,
                vty_acl=mgmt_name,
                default_gateway=mgmt.gateway,
            )
        )
    return devices


def _metro_devices(plan) -> list[DeviceConfig]:
    scenario = plan.scenario
    vlans = _vlans(plan)
    allowed = _allowed(plan)
    native = scenario.native_vlan
    hub = _hub_site(scenario)
    mgmt_acl, mgmt_name = _mgmt_acl(plan)
    trading = _find_block(plan, "trading")

    devices: list[DeviceConfig] = []
    hub_interfaces: list[InterfaceDef] = [
        InterfaceDef("GigabitEthernet0/0", "LAN trunk", "physical")
    ]
    hub_networks: list[tuple[str, str, int]] = []
    hub_passive: list[str] = []
    for block in _lan_blocks(plan):
        if (block.site or "") != hub.name:
            continue
        hub_interfaces.append(
            InterfaceDef(
                f"GigabitEthernet0/0.{block.vlan}",
                block.name,
                "svi",
                vlan=block.vlan,
                ip=block.gateway,
                mask=block.mask,
            )
        )
        hub_networks.append((block.network, block.wildcard, 0))
        hub_passive.append(f"GigabitEthernet0/0.{block.vlan}")

    remotes = [site for site in scenario.sites if site.name != hub.name]
    for index, site in enumerate(remotes):
        link = _p2p(plan, hub.name, site.name)
        if link is None:
            raise ValueError(f"missing point-to-point block between {hub.name} and {site.name}")
        serial = SERIAL_NAMES[index]
        hub_interfaces.append(
            InterfaceDef(
                serial,
                f"WAN link to {site.name}",
                "routed",
                ip=_ip(link, 1),
                mask=link.mask,
                clock_rate=1544000,
                qos=True,
            )
        )
        hub_networks.append((link.network, link.wildcard, 0))

    devices.append(
        DeviceConfig(
            hostname=f"{scenario.name}-hq-rtr",
            role="HQ router (ABR)",
            l3=True,
            vlans=list(vlans),
            interfaces=hub_interfaces,
            ospf=OspfDef(1, _mgmt(plan).gateway, hub_networks, hub_passive, []),
            acls=[mgmt_acl],
            qos=trading is not None,
            qos_network=trading.network if trading else None,
            qos_wildcard=trading.wildcard if trading else None,
            vty_acl=mgmt_name,
        )
    )

    for index, site in enumerate(remotes):
        link = _p2p(plan, hub.name, site.name)
        lan = _site_block(plan, site.name)
        if link is None or lan is None:
            raise ValueError(f"incomplete site {site.name}")
        serial = SERIAL_NAMES[0]
        interfaces = [
            InterfaceDef("GigabitEthernet0/0", "LAN trunk", "physical"),
            InterfaceDef(
                f"GigabitEthernet0/0.{lan.vlan}",
                lan.name,
                "svi",
                vlan=lan.vlan,
                ip=lan.gateway,
                mask=lan.mask,
            ),
            InterfaceDef(
                serial,
                f"WAN link to {hub.name}",
                "routed",
                ip=_ip(link, 2),
                mask=link.mask,
            ),
        ]
        area = plan.routing.area_for_site.get(site.name, index + 1)
        networks = [
            (lan.network, lan.wildcard, area),
            (link.network, link.wildcard, 0),
        ]
        ranges = [
            (summary.area, summary.network, summary.mask)
            for summary in plan.routing.summaries
            if summary.site.lower() == site.name.lower() and not summary.exact
        ]
        devices.append(
            DeviceConfig(
                hostname=f"{scenario.name}-{site.name.lower()}-rtr",
                role=f"{site.name} router (ABR)",
                l3=True,
                vlans=[VlanDef(lan.vlan, _vlan_name(lan.name))] if lan.vlan else [],
                interfaces=interfaces,
                ospf=OspfDef(1, lan.gateway, networks, [f"GigabitEthernet0/0.{lan.vlan}"], ranges),
                acls=[mgmt_acl],
                vty_acl=mgmt_name,
            )
        )

    for site in scenario.sites:
        lan = _site_block(plan, site.name)
        if lan is None:
            continue
        site_vlans = [block for block in _lan_blocks(plan) if (block.site or "") == site.name]
        interfaces = [
            InterfaceDef(
                "GigabitEthernet0/1",
                "Trunk to router",
                "trunk",
                allowed_vlans=sorted(block.vlan for block in site_vlans if block.vlan),
                native_vlan=native,
            )
        ]
        for port in range(1, 25):
            block = site_vlans[(port - 1) % len(site_vlans)]
            interfaces.append(
                InterfaceDef(
                    f"FastEthernet0/{port}",
                    f"Access port {port}",
                    "access",
                    vlan=block.vlan,
                )
            )
        interfaces.append(
            InterfaceDef(
                f"Vlan{lan.vlan}",
                "Management SVI",
                "svi",
                ip=_ip(lan, 10),
                mask=lan.mask,
            )
        )
        devices.append(
            DeviceConfig(
                hostname=f"{scenario.name}-{site.name.lower()}-sw",
                role=f"{site.name} access switch",
                vlans=[VlanDef(block.vlan, _vlan_name(block.name)) for block in site_vlans if block.vlan],
                interfaces=interfaces,
                acls=[mgmt_acl],
                stp_mode=plan.switching.stp_mode,
                vty_acl=mgmt_name,
                default_gateway=lan.gateway,
            )
        )
    return devices


def _wan_devices(plan) -> list[DeviceConfig]:
    scenario = plan.scenario
    hub = _hub_site(scenario)
    cloud_site = next(site for site in scenario.sites if site.role == "cloud")
    cities = [site for site in scenario.sites if site.name not in {hub.name, cloud_site.name}]
    cloud_link = _p2p(plan, hub.name, cloud_site.name)
    if cloud_link is None:
        raise ValueError("WAN plan needs a point-to-point link to the cloud")
    cloud_peer_ip = _ip(cloud_link, 2)
    hub_peer_ip = _ip(cloud_link, 1)
    hub_lan = _site_block(plan, hub.name)
    cloud_lan = _site_block(plan, cloud_site.name)
    if hub_lan is None or cloud_lan is None:
        raise ValueError("WAN plan needs a hub LAN and a cloud LAN")

    mgmt_acl, mgmt_name = _mgmt_acl(plan)
    vlans = _vlans(plan)
    native = scenario.native_vlan
    devices: list[DeviceConfig] = []

    hub_interfaces: list[InterfaceDef] = [
        InterfaceDef("GigabitEthernet0/0", "LAN trunk", "physical")
    ]
    hub_interfaces.append(
        InterfaceDef(
            f"GigabitEthernet0/0.{hub_lan.vlan}",
            hub_lan.name,
            "svi",
            vlan=hub_lan.vlan,
            ip=hub_lan.gateway,
            mask=hub_lan.mask,
        )
    )
    hub_networks: list[tuple[str, str, int]] = [(hub_lan.network, hub_lan.wildcard, 0)]
    for index, city in enumerate(cities):
        link = _p2p(plan, hub.name, city.name)
        if link is None:
            raise ValueError(f"missing WAN link between {hub.name} and {city.name}")
        serial = SERIAL_NAMES[index]
        hub_interfaces.append(
            InterfaceDef(
                serial,
                f"WAN link to {city.name}",
                "routed",
                ip=_ip(link, 1),
                mask=link.mask,
                clock_rate=1544000,
                qos=True,
            )
        )
        hub_networks.append((link.network, link.wildcard, 0))
    hub_interfaces.append(
        InterfaceDef(
            "GigabitEthernet0/1",
            "Cloud VPC boundary",
            "routed",
            ip=hub_peer_ip,
            mask=cloud_link.mask,
            crypto_map=True,
        )
    )
    hub_networks.append((cloud_link.network, cloud_link.wildcard, 0))

    bgp_networks = [
        (block.network, block.mask)
        for block in _lan_blocks(plan)
        if (block.site or "") != cloud_site.name
    ]
    devices.append(
        DeviceConfig(
            hostname=f"{scenario.name}-{hub.name.lower()}-rtr",
            role="Hub router (OSPF ABR + eBGP speaker)",
            l3=True,
            vlans=list(vlans),
            interfaces=hub_interfaces,
            ospf=OspfDef(1, _mgmt(plan).gateway, hub_networks, [f"GigabitEthernet0/0.{hub_lan.vlan}"], []),
            bgp=BgpDef(
                local_asn=scenario.local_asn or 65010,
                neighbors=[(cloud_peer_ip, scenario.peer_asn or 64512)],
                networks=bgp_networks,
            ),
            acls=[mgmt_acl],
            ipsec=IpsecDef(
                peer=cloud_peer_ip,
                local_network=hub_lan.network,
                local_wildcard=hub_lan.wildcard,
                remote_network=cloud_lan.network,
                remote_wildcard=cloud_lan.wildcard,
                map_name=f"{scenario.name.upper()}-MAP",
            ),
            qos=True,
            qos_network=hub_lan.network,
            qos_wildcard=hub_lan.wildcard,
            vty_acl=mgmt_name,
        )
    )

    for index, city in enumerate(cities):
        link = _p2p(plan, hub.name, city.name)
        lan = _site_block(plan, city.name)
        if link is None or lan is None:
            raise ValueError(f"incomplete WAN city {city.name}")
        interfaces = [
            InterfaceDef("GigabitEthernet0/0", "LAN trunk", "physical"),
            InterfaceDef(
                f"GigabitEthernet0/0.{lan.vlan}",
                lan.name,
                "svi",
                vlan=lan.vlan,
                ip=lan.gateway,
                mask=lan.mask,
            ),
            InterfaceDef(
                SERIAL_NAMES[0],
                f"WAN link to {hub.name}",
                "routed",
                ip=_ip(link, 2),
                mask=link.mask,
                qos=True,
            ),
        ]
        area = plan.routing.area_for_site.get(city.name, index + 1)
        ranges = [
            (summary.area, summary.network, summary.mask)
            for summary in plan.routing.summaries
            if summary.site.lower() == city.name.lower() and not summary.exact
        ]
        devices.append(
            DeviceConfig(
                hostname=f"{scenario.name}-{city.name.lower()}-rtr",
                role=f"{city.name} router (ABR)",
                l3=True,
                vlans=[VlanDef(lan.vlan, _vlan_name(lan.name))] if lan.vlan else [],
                interfaces=interfaces,
                ospf=OspfDef(
                    1,
                    lan.gateway,
                    [(lan.network, lan.wildcard, area), (link.network, link.wildcard, 0)],
                    [f"GigabitEthernet0/0.{lan.vlan}"],
                    ranges,
                ),
                acls=[mgmt_acl],
                qos=True,
                qos_network=lan.network,
                qos_wildcard=lan.wildcard,
                vty_acl=mgmt_name,
            )
        )

    devices.append(
        DeviceConfig(
            hostname=f"{scenario.name}-cloud-rtr",
            role="Cloud VPC eBGP peer",
            l3=True,
            interfaces=[
                InterfaceDef(
                    "GigabitEthernet0/0",
                    f"WAN link to {hub.name}",
                    "routed",
                    ip=cloud_peer_ip,
                    mask=cloud_link.mask,
                    crypto_map=True,
                ),
                InterfaceDef("Loopback0", "Cloud VPC loopback", "loopback", ip="203.0.113.1", mask="255.255.255.255"),
            ],
            bgp=BgpDef(
                local_asn=scenario.peer_asn or 64512,
                neighbors=[(hub_peer_ip, scenario.local_asn or 65010)],
                networks=[(cloud_lan.network, cloud_lan.mask)],
            ),
            acls=[mgmt_acl],
            ipsec=IpsecDef(
                peer=hub_peer_ip,
                local_network=cloud_lan.network,
                local_wildcard=cloud_lan.wildcard,
                remote_network=hub_lan.network,
                remote_wildcard=hub_lan.wildcard,
                map_name=f"{scenario.name.upper()}-MAP",
            ),
            vty_acl=mgmt_name,
        )
    )

    for city in [hub, *cities]:
        lan = _site_block(plan, city.name)
        if lan is None:
            continue
        interfaces = [
            InterfaceDef(
                "GigabitEthernet0/1",
                "Trunk to router",
                "trunk",
                allowed_vlans=[lan.vlan] if lan.vlan else [],
                native_vlan=native,
            )
        ]
        for port in range(1, 25):
            interfaces.append(
                InterfaceDef(f"FastEthernet0/{port}", f"Access port {port}", "access", vlan=lan.vlan)
            )
        interfaces.append(
            InterfaceDef(
                f"Vlan{lan.vlan}",
                "Management SVI",
                "svi",
                ip=_ip(lan, 10),
                mask=lan.mask,
            )
        )
        devices.append(
            DeviceConfig(
                hostname=f"{scenario.name}-{city.name.lower()}-sw",
                role=f"{city.name} access switch",
                vlans=[VlanDef(lan.vlan, _vlan_name(lan.name))] if lan.vlan else [],
                interfaces=interfaces,
                acls=[mgmt_acl],
                stp_mode=plan.switching.stp_mode,
                vty_acl=mgmt_name,
                default_gateway=lan.gateway,
            )
        )
    return devices


def build_devices(plan) -> list[DeviceConfig]:
    """Pick the device template that matches the scenario shape."""
    if plan.scenario.cloud:
        return _wan_devices(plan)
    if len(plan.scenario.sites) > 1:
        return _metro_devices(plan)
    return _campus_devices(plan)


_ENV = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def render_device(device: DeviceConfig, scenario: Scenario) -> str:
    template = _ENV.get_template("ios_device.j2")
    return template.render(device=device, scenario=scenario, lab_secret=LAB_SECRET)


def build_configs(plan) -> tuple[dict[str, str], str]:
    """Return ``({hostname: config}, combined_export_text)``."""
    devices = build_devices(plan)
    rendered: dict[str, str] = {}
    chunks: list[str] = [
        "! NetArchitect export",
        f"! Preset: {plan.scenario.name}",
        f"! Devices: {len(devices)}",
        "! Split this file at each DEVICE banner and paste one block",
        "! per device, from the hostname line through end, in configuration mode.",
        "!",
        "",
    ]
    for device in devices:
        config = render_device(device, plan.scenario)
        rendered[device.hostname] = config
        chunks.append(f"! ===== DEVICE: {device.hostname} =====")
        chunks.append(config.rstrip())
        chunks.append("")
    return rendered, "\n".join(chunks).rstrip() + "\n"
