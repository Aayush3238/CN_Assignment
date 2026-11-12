"""Layer-3 routing and area planning.

The decision table is enforced literally:

* cloud boundary or more than one autonomous system -> multi-area OSPF + eBGP;
* otherwise, more than one site **and** a link longer than 400 m, or 50 or
  more subnets -> multi-area OSPF with one summary per site;
* every remaining case -> single-area OSPF Area 0.

eBGP needs ``local_asn`` and ``peer_asn``.  The engine never invents an AS
number; a missing one is a validation error.

Summaries are the shortest prefix covering a site.  If that cover would also
contain another site's blocks, the site advertises its exact prefixes instead,
which prevents the wrong-area loop described in the audit log.
"""

from __future__ import annotations

from dataclasses import dataclass

from netarchitect.core.errors import InvalidParameterError
from netarchitect.core.ipv4 import (
    common_prefix,
    format_cidr,
    format_ipv4,
    network_of,
    prefix_mask,
)
from netarchitect.core.spec import Scenario
from netarchitect.core.vlsm import SubnetBlock

MULTI_AREA_SUBNET_LIMIT = 50
LONG_LINK_M = 400.0
CORE_ROLES = {"hq", "core", "hub", "cloud"}


@dataclass(frozen=True)
class OspfNetwork:
    name: str
    network: str
    wildcard: str
    mask: str
    area: int
    cidr: str
    passive: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "network": self.network,
            "wildcard": self.wildcard,
            "mask": self.mask,
            "area": self.area,
            "cidr": self.cidr,
            "passive": self.passive,
        }


@dataclass(frozen=True)
class AreaSummary:
    area: int
    site: str
    network: str
    mask: str
    cidr: str
    exact: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "area": self.area,
            "site": self.site,
            "network": self.network,
            "mask": self.mask,
            "cidr": self.cidr,
            "exact": self.exact,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RoutingPlan:
    protocol: str
    area_for_site: dict[str, int]
    networks: tuple[OspfNetwork, ...]
    summaries: tuple[AreaSummary, ...]
    bgp: bool
    local_asn: int | None
    peer_asn: int | None
    reason: str
    violation: str | None
    alternatives: tuple[str, ...] = ()

    @property
    def area0(self) -> bool:
        return self.protocol == "OSPF Area 0"

    @property
    def multi_area(self) -> bool:
        return "Multi-area" in self.protocol

    def networks_for_area(self, area: int) -> list[OspfNetwork]:
        return [network for network in self.networks if network.area == area]

    def to_dict(self) -> dict[str, object]:
        areas: dict[int, list[str]] = {}
        for network in self.networks:
            areas.setdefault(network.area, []).append(network.cidr)
        return {
            "protocol": self.protocol,
            "area_for_site": dict(self.area_for_site),
            "areas": {str(area): cidrs for area, cidrs in sorted(areas.items())},
            "networks": [network.to_dict() for network in self.networks],
            "summaries": [summary.to_dict() for summary in self.summaries],
            "bgp": self.bgp,
            "local_asn": self.local_asn,
            "peer_asn": self.peer_asn,
            "reason": self.reason,
            "violation": self.violation,
            "alternatives": list(self.alternatives),
        }


def _site_areas(scenario: Scenario) -> dict[str, int]:
    """Assign area 0 to the core/HQ site and 1..N to the rest."""
    sites = list(scenario.sites)
    if not sites:
        return {}
    core_name: str | None = None
    for site in sites:
        if site.role in CORE_ROLES:
            core_name = site.name
            break
    if core_name is None:
        core_name = sites[0].name

    mapping: dict[str, int] = {core_name: 0}
    next_area = 1
    for site in sites:
        if site.name == core_name:
            continue
        if site.role in CORE_ROLES:  # e.g. a cloud boundary shares area 0
            mapping[site.name] = 0
            continue
        mapping[site.name] = next_area
        next_area += 1
    return mapping


def _block_site(scenario: Scenario, block: SubnetBlock) -> str | None:
    if block.site:
        return block.site
    return scenario.site_of(block.name)


def _summaries(
    scenario: Scenario,
    blocks: list[SubnetBlock],
    area_for_site: dict[str, int],
) -> tuple[AreaSummary, ...]:
    summaries: list[AreaSummary] = []
    by_site: dict[str, list[SubnetBlock]] = {}
    for block in blocks:
        if block.point_to_point:
            continue
        site = _block_site(scenario, block)
        if site is None:
            continue
        by_site.setdefault(site, []).append(block)

    for site, site_blocks in by_site.items():
        area = area_for_site.get(site, 0)
        if area == 0:
            continue
        cover = common_prefix([(block.network_int, block.prefix) for block in site_blocks])
        if cover is None:  # pragma: no cover - site_blocks is non-empty
            continue
        cover_network, cover_prefix = cover
        other_blocks = [
            block
            for other, members in by_site.items()
            if other != site
            for block in members
        ]
        covers_other = any(
            network_of(block.network_int, cover_prefix) == cover_network
            for block in other_blocks
        )
        if covers_other:
            for block in site_blocks:
                summaries.append(
                    AreaSummary(
                        area=area,
                        site=site,
                        network=block.network,
                        mask=block.mask,
                        cidr=block.cidr,
                        exact=True,
                        reason=(
                            f"Area {area} ({site}) advertises the exact prefix "
                            f"{block.cidr} because the shortest cover "
                            f"{format_cidr(cover_network, cover_prefix)} would also "
                            "contain another site."
                        ),
                    )
                )
        else:
            summaries.append(
                AreaSummary(
                    area=area,
                    site=site,
                    network=format_ipv4(cover_network),
                    mask=format_ipv4(prefix_mask(cover_prefix)),
                    cidr=format_cidr(cover_network, cover_prefix),
                    exact=False,
                    reason=(
                        f"Area {area} ({site}) is summarised as "
                        f"{format_cidr(cover_network, cover_prefix)}, the shortest "
                        f"prefix covering {len(site_blocks)} block(s), and it does "
                        "not contain another site."
                    ),
                )
            )
    return tuple(summaries)


def decide_routing(
    scenario: Scenario,
    blocks: tuple[SubnetBlock, ...] | list[SubnetBlock],
    mode: str | None = None,
) -> RoutingPlan:
    """Choose the routing protocol and build the area plan."""
    block_list = list(blocks)
    multi_site = len(scenario.sites) > 1
    long_link = any(link.distance_m > LONG_LINK_M for link in scenario.links)
    many_subnets = len(block_list) >= MULTI_AREA_SUBNET_LIMIT
    natural_multi = (multi_site and long_link) or many_subnets
    bgp_required = scenario.cloud or not scenario.single_as

    if bgp_required:
        if scenario.local_asn is None or scenario.peer_asn is None:
            raise InvalidParameterError(
                "eBGP requires local_asn and peer_asn; the engine does not "
                "invent autonomous-system numbers"
            )

    normalised = None
    if mode is not None:
        normalised = mode.strip().lower().replace("_", "-")
        aliases = {
            "area0": "area0",
            "area-0": "area0",
            "single-area": "area0",
            "single": "area0",
            "multi": "multi-area",
            "multi-area": "multi-area",
            "multiarea": "multi-area",
            "bgp": "bgp",
        }
        if normalised not in aliases:
            raise ValueError(f"unknown routing mode: {mode!r}")
        normalised = aliases[normalised]

    protocol: str
    violation: str | None = None
    if normalised == "area0":
        protocol = "OSPF Area 0"
        if bgp_required:
            violation = (
                "Single-area OSPF omits the eBGP cloud boundary; the scenario "
                "contains a cloud VPC or more than one autonomous system."
            )
        elif natural_multi:
            violation = (
                "Single-area OSPF ignores the multi-site rule: more than one site "
                "with a link longer than 400 m, or 50 or more subnets."
            )
    elif normalised == "multi-area":
        protocol = "Multi-area OSPF"
        if bgp_required:
            violation = (
                "Multi-area OSPF alone omits the eBGP boundary required by the "
                "cloud VPC or second autonomous system."
            )
    elif normalised == "bgp":
        protocol = "Multi-area OSPF + eBGP"
        if not bgp_required:
            violation = (
                "eBGP is unnecessary: the scenario has one autonomous system and "
                "no cloud boundary."
            )
    elif bgp_required:
        protocol = "Multi-area OSPF + eBGP"
    elif natural_multi:
        protocol = "Multi-area OSPF"
    else:
        protocol = "OSPF Area 0"

    effective_multi = protocol != "OSPF Area 0"
    bgp = protocol.endswith("+ eBGP")
    area_for_site = _site_areas(scenario) if effective_multi else {
        site.name: 0 for site in scenario.sites
    }

    cloud_sites = {
        site.name.lower() for site in scenario.sites if site.role == "cloud"
    }
    networks: list[OspfNetwork] = []
    for block in block_list:
        if effective_multi and not block.point_to_point:
            site = _block_site(scenario, block)
            if bgp and site is not None and site.lower() in cloud_sites:
                # The cloud VPC is advertised by eBGP, not by OSPF.
                continue
            area = area_for_site.get(site or "", 0)
        else:
            area = 0
        networks.append(
            OspfNetwork(
                name=block.name,
                network=block.network,
                wildcard=block.wildcard,
                mask=block.mask,
                area=area,
                cidr=block.cidr,
                passive=not block.point_to_point,
            )
        )

    summaries = _summaries(scenario, block_list, area_for_site) if effective_multi else ()

    if bgp:
        reason = (
            f"Selected multi-area OSPF plus eBGP because the scenario contains a "
            f"cloud boundary ({scenario.cloud}) or more than one autonomous system "
            f"(single_as={scenario.single_as}). OSPF Area 0 carries the internal "
            f"topology with per-site areas and summaries (RFC 2328); eBGP "
            f"advertises the internal prefixes to AS {scenario.peer_asn} from "
            f"AS {scenario.local_asn} and isolates the routing domains (RFC 4271)."
        )
    elif effective_multi:
        reason = (
            f"Selected multi-area OSPF because {len(scenario.sites)} sites and a "
            f"longest link of "
            f"{max((link.distance_m for link in scenario.links if link.kind != 'access'), default=max(link.distance_m for link in scenario.links)):.0f} m"
            f" exceed the 400 m single-site assumption, or the plan has "
            f"{len(block_list)} subnets (>= {MULTI_AREA_SUBNET_LIMIT}). Area 0 is "
            "the backbone; each remote site gets its own area and a summary, so a "
            "topology change in one site does not flood the others (RFC 2328)."
        )
    else:
        reason = (
            f"Selected single-area OSPF Area 0 because the scenario has one site, "
            f"one autonomous system, {len(block_list)} subnets (< "
            f"{MULTI_AREA_SUBNET_LIMIT}), and no inter-site link longer than 400 m. "
            "A single link-state area converges quickly and keeps the design "
            "simple (RFC 2328)."
        )

    return RoutingPlan(
        protocol=protocol,
        area_for_site=area_for_site,
        networks=tuple(networks),
        summaries=summaries,
        bgp=bgp,
        local_asn=scenario.local_asn,
        peer_asn=scenario.peer_asn,
        reason=reason,
        violation=violation,
        alternatives=(
            "IS-IS is a link-state alternative, but OSPF is the Cisco-native "
            "choice for this course and Packet Tracer.",
        ),
    )
