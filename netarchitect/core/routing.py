"""Layer-3 routing protocol selection.

The assignment's decision table is enforced here:
* one autonomous system with < 50 subnets -> single-area OSPF Area 0
* multi-site / multi-cloud boundary    -> multi-area OSPF and/or eBGP
* >= 50 subnets in one AS              -> multi-area OSPF (area isolation)

OSPF areas are also assigned and summarisation candidates are derived from the
allocated subnets using :func:`ipaddress.collapse_addresses`.
"""

from __future__ import annotations

import ipaddress

from netarchitect.core.models import RoutingDecision, ScenarioInput, Subnet

OSPF_SINGLE_AREA_LIMIT = 50


def _assign_areas(cidrs: list[str], multi_area: bool) -> dict[str, list[str]]:
    """Assign subnets to OSPF areas.

    For small single-site designs everything stays in Area 0. In multi-area
    designs the first two subnets form the Area 0 transit core and the
    remaining subnets are split into areas 10, 20, 30... two at a time.
    """
    if not multi_area or len(cidrs) <= 2:
        return {"0": list(cidrs)}

    areas: dict[str, list[str]] = {}
    for index, cidr in enumerate(cidrs):
        if index < 2:
            area = "0"
        else:
            area = str(10 * (((index - 2) // 2) + 1))
        areas.setdefault(area, []).append(cidr)
    return areas


def _summarisation_commands(areas: dict[str, list[str]]) -> list[str]:
    """Return OSPF ``area X range`` commands for blocks that actually summarise.

    ``collapse_addresses`` groups contiguous networks into the shortest possible
    summary. We only emit a command when collapsing genuinely reduces the number
    of advertisements, which keeps the config free of no-op summaries.
    """
    commands: list[str] = []
    for area, cidrs in areas.items():
        networks = [ipaddress.ip_network(cidr) for cidr in cidrs]
        collapsed = list(ipaddress.collapse_addresses(networks))
        if len(collapsed) < len(networks):
            for summary in collapsed:
                commands.append(
                    f"area {area} range {summary.network_address} {summary.netmask}"
                )
    return commands


def decide_routing(scenario: ScenarioInput, subnets: list[Subnet]) -> RoutingDecision:
    """Select the routing protocol and build the area/summary plan."""
    subnet_count = len(subnets)
    cidrs = [subnet.cidr for subnet in subnets]

    # A Cloud VPC is the strongest signal: it needs a routing-domain boundary.
    if scenario.cloud_vpc:
        rule_id = "L3-ROUTE-03"
        protocol = "Multi-Area OSPF + eBGP (cloud boundary)"
        rationale = (
            f"Selected multi-area OSPF inside the enterprise and eBGP at the cloud "
            f"VPC boundary because the design includes a cloud VPC plus "
            f"{scenario.remote_sites} remote site(s). eBGP provides routing-domain "
            "isolation and policy control, while OSPF areas contain internal "
            "topology changes and allow summarisation."
        )
        standard = "RFC 2328 (OSPFv2), RFC 4271 (BGP-4)"
        multi_area = True
    elif (
        scenario.remote_sites > 0
        or scenario.wan_distance_m > 400
        or subnet_count >= OSPF_SINGLE_AREA_LIMIT
    ):
        rule_id = "L3-ROUTE-02"
        protocol = "Multi-Area OSPF"
        rationale = (
            f"Selected multi-area OSPF because the design spans "
            f"{max(scenario.remote_sites, 1)} remote site/WAN link(s) or exceeds "
            f"{OSPF_SINGLE_AREA_LIMIT} subnets. Area 0 remains the transit core, "
            "while remote areas isolate SPF churn and permit route summarisation."
        )
        standard = "RFC 2328 (OSPFv2)"
        multi_area = True
    else:
        rule_id = "L3-ROUTE-01"
        protocol = "OSPF Area 0 (single area)"
        rationale = (
            f"Selected single-area OSPF (Area 0) because the scenario contains "
            f"{subnet_count} subnet(s), fewer than {OSPF_SINGLE_AREA_LIMIT}, inside "
            "one autonomous system. Link-state convergence is fast and the flat "
            "area keeps the design simple to operate."
        )
        standard = "RFC 2328 (OSPFv2)"
        multi_area = False

    areas = _assign_areas(cidrs, multi_area)
    return RoutingDecision(
        protocol=protocol,
        areas=areas,
        rationale=rationale,
        rule_id=rule_id,
        summarization=_summarisation_commands(areas),
    )
