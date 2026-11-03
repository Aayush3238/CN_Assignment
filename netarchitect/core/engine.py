"""Top-level orchestration for one architecture run.

The engine is intentionally linear and side-effect free:
    media -> VLSM -> routing -> VLANs -> IOS configs -> rationale log

Every stage appends a justification to the collector, so the final ``RunResult``
contains both the design and the reasoning behind it.
"""

from __future__ import annotations

from netarchitect.configs.ios import build_configs
from netarchitect.core.explain import RationaleCollector
from netarchitect.core.models import RunResult, ScenarioInput
from netarchitect.core.physics import select_media
from netarchitect.core.routing import decide_routing
from netarchitect.core.vlan import build_vlan_plan
from netarchitect.core.vlsm import VLSMRequest, allocate_vlsm


def run_scenario(scenario: ScenarioInput) -> RunResult:
    """Execute the full rule engine for a validated scenario."""
    collector = RationaleCollector()

    # --- L1: media selection -------------------------------------------------
    media = []
    for link in scenario.links():
        recommendation = select_media(link)
        media.append(recommendation)
        collector.add(
            rule_id=recommendation.rule_id,
            domain="L1",
            inputs={
                "link": link.name,
                "distance_m": link.distance_m,
                "category": link.category,
                "requested_media": link.requested_media,
            },
            condition=(
                f"{link.distance_m:g} m on {link.category} link "
                f"(requested: {link.requested_media})"
            ),
            choice=f"{recommendation.media} / {recommendation.transceiver}",
            rationale=recommendation.rationale,
            standard=recommendation.standard,
        )

    # --- L3 addressing: VLSM -------------------------------------------------
    requests = [
        VLSMRequest(name=vlan.name, hosts=vlan.hosts) for vlan in scenario.vlans
    ]
    allocation = allocate_vlsm(scenario.root_prefix, requests)

    collector.add(
        rule_id="VLSM-ALLOC",
        domain="VLSM",
        inputs={
            "root_prefix": allocation.utilization.root_prefix,
            "requests": {vlan.name: vlan.hosts for vlan in scenario.vlans},
        },
        condition="largest-first allocation with CIDR boundary alignment",
        choice=f"{len(allocation.subnets)} non-overlapping subnets",
        rationale=(
            f"Allocated {len(allocation.subnets)} subnets from "
            f"{allocation.utilization.root_prefix} using largest-first VLSM. "
            f"Address-space utilisation is {allocation.utilization.address_pct:.2f}% "
            f"and host utilisation is {allocation.utilization.host_pct:.2f}%."
        ),
        standard="RFC 4632 (CIDR)",
    )

    for subnet in allocation.subnets:
        collector.add(
            rule_id="VLSM-BLOCK",
            domain="VLSM",
            inputs={
                "name": subnet.name,
                "requested_hosts": subnet.requested_hosts,
                "cidr": subnet.cidr,
            },
            condition=(
                f"needed {subnet.requested_hosts} usable host(s) plus network/broadcast"
            ),
            choice=f"{subnet.name} -> {subnet.cidr}",
            rationale=(
                f"Allocated {subnet.cidr} to {subnet.name}: "
                f"{subnet.usable_hosts} usable addresses, gateway {subnet.gateway}, "
                f"wildcard {subnet.wildcard}. Blocks are aligned and checked for "
                "overlap with all previously allocated subnets."
            ),
            standard="RFC 4632 (CIDR)",
        )

    # --- L3 routing ----------------------------------------------------------
    routing = decide_routing(scenario, allocation.subnets)
    collector.add(
        rule_id=routing.rule_id,
        domain="L3",
        inputs={
            "subnet_count": len(allocation.subnets),
            "remote_sites": scenario.remote_sites,
            "cloud_vpc": scenario.cloud_vpc,
            "wan_distance_m": scenario.wan_distance_m,
        },
        condition="single-AS vs multi-site/cloud boundary",
        choice=routing.protocol,
        rationale=routing.rationale,
        standard="RFC 2328 (OSPFv2), RFC 4271 (BGP-4)",
    )

    # --- L2 VLAN / RSTP / PoE ------------------------------------------------
    vlans = build_vlan_plan(scenario, allocation.subnets)
    for vlan in vlans:
        collector.add(
            rule_id="VLAN-8021Q",
            domain="L2",
            inputs={
                "vlan_id": vlan.vlan_id,
                "name": vlan.name,
                "subnet": vlan.subnet,
                "trunk_allowed": vlan.trunk_allowed,
            },
            condition="segmentation by function with explicit trunk policy",
            choice=f"VLAN {vlan.vlan_id} ({vlan.name})",
            rationale=vlan.rationale,
            standard="IEEE 802.1Q",
        )

    collector.add(
        rule_id="L2-RSTP",
        domain="L2",
        inputs={"vlan_count": len(vlans), "resiliency": scenario.resiliency},
        condition="loop prevention with deterministic root selection",
        choice="Rapid PVST+",
        rationale=(
            "Selected Rapid PVST+ with per-VLAN root priority 4096 on the "
            "management VLAN so that each VLAN has a deterministic root and "
            "sub-second reconvergence after a topology change."
        ),
        standard="IEEE 802.1w",
    )

    if scenario.resiliency != "single-homed":
        collector.add(
            rule_id="L2-RESILIENCY",
            domain="L2",
            inputs={"resiliency": scenario.resiliency},
            condition="scenario requires non-single-homed availability",
            choice=f"{scenario.resiliency} uplinks + HSRP/VRRP peer",
            rationale=(
                f"Selected {scenario.resiliency} design with a paired gateway "
                "peer because the scenario requests resilience beyond a single "
                "uplink. HSRP/VRRP removes the gateway as a single point of failure."
            ),
            standard="RFC 5798 (VRRP)",
        )

    if scenario.qos_latency_ms is not None:
        collector.add(
            rule_id="L3-QOS",
            domain="QoS",
            inputs={
                "latency_target_ms": scenario.qos_latency_ms,
                "uplink_gbps": scenario.uplink_gbps,
            },
            condition="latency-sensitive traffic on the WAN",
            choice="EF priority queue + CS3 signalling bandwidth",
            rationale=(
                f"Selected a strict priority queue for DSCP EF and a reserved "
                f"bandwidth class for CS3 because the scenario requires "
                f"{scenario.qos_latency_ms:g} ms application latency. Lower "
                "latency-sensitive traffic is shaped by class-default."
            ),
            standard="RFC 2474 / RFC 2475 (DiffServ)",
        )

    if scenario.cloud_vpc or (
        scenario.wan_service == "internet" and scenario.wan_distance_m > 0
    ):
        collector.add(
            rule_id="L3-VPN",
            domain="Security",
            inputs={
                "cloud_vpc": scenario.cloud_vpc,
                "wan_service": scenario.wan_service,
            },
            condition="traffic crosses an untrusted public WAN",
            choice="IPsec tunnel (AES-256/SHA-256)",
            rationale=(
                "Selected an IPsec VPN overlay because the WAN crosses public "
                "infrastructure. AES-256/SHA-256 provides confidentiality and "
                "integrity, and the tunnel policy limits interesting traffic to "
                "the enterprise/cloud prefixes."
            ),
            standard="RFC 4301 (IPsec)",
        )

    # --- Export-ready configurations ----------------------------------------
    configs = build_configs(scenario, media, allocation.subnets, vlans, routing)

    return RunResult(
        scenario=scenario,
        media=media,
        vlans=vlans,
        routing=routing,
        subnets=allocation.subnets,
        utilization=allocation.utilization,
        rationales=collector.entries,
        configs=configs,
    )
