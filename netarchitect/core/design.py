"""Top-level orchestration: design() and analyze().

``design`` is the headless rule engine.  ``analyze`` adds the alternate plan
and the rendered Cisco IOS, and is the single entry point used by both the CLI
and the web dashboard.  Neither interface recalculates a mask or an optical
budget; they only format what these objects contain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from netarchitect.core.errors import NetArchitectError
from netarchitect.core.media import MediaChoice, select_media
from netarchitect.core.routing import RoutingPlan, decide_routing
from netarchitect.core.spec import Scenario
from netarchitect.core.switching import SwitchingPlan, decide_switching
from netarchitect.core.topology import TopologyPlan, plan_topology
from netarchitect.core.vlsm import VLSMPlan, allocate_vlsm


@dataclass(frozen=True)
class Decision:
    category: str
    choice: str
    reason: str
    standard: str
    severity: str = "info"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "choice": self.choice,
            "reason": self.reason,
            "standard": self.standard,
            "severity": self.severity,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class Plan:
    scenario: Scenario
    media: tuple[MediaChoice, ...]
    vlsm: VLSMPlan
    topology: TopologyPlan
    routing: RoutingPlan
    switching: SwitchingPlan
    decisions: tuple[Decision, ...]
    violations: tuple[str, ...] = ()
    tier_override: str | None = None
    routing_override: str | None = None

    @property
    def name(self) -> str:
        return self.scenario.name

    def decisions_for(self, category: str) -> list[Decision]:
        needle = category.lower()
        return [item for item in self.decisions if needle in item.category.lower()]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.to_dict(),
            "media": [item.to_dict() for item in self.media],
            "vlsm": self.vlsm.to_dict(),
            "topology": self.topology.to_dict(),
            "routing": self.routing.to_dict(),
            "switching": self.switching.to_dict(),
            "decisions": [item.to_dict() for item in self.decisions],
            "violations": list(self.violations),
        }


@dataclass(frozen=True)
class Analysis:
    scenario: Scenario
    selected: Plan
    alternate: Plan
    device_configs: dict[str, str]
    export_text: str
    export_filename: str

    def to_dict(self, include_configs: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scenario": self.scenario.to_dict(),
            "selected": self.selected.to_dict(),
            "alternate": self.alternate.to_dict(),
            "export_filename": self.export_filename,
            "devices": sorted(self.device_configs),
        }
        if include_configs:
            payload["device_configs"] = dict(self.device_configs)
        return payload


def _media_decisions(media: tuple[MediaChoice, ...]) -> list[Decision]:
    decisions: list[Decision] = []
    for item in media:
        decisions.append(
            Decision(
                category="Physical media (L1)",
                choice=f"{item.medium} / {item.transceiver}",
                reason=item.reason,
                standard=item.standard,
                severity=item.severity,
                evidence=item.evidence,
            )
        )
    return decisions


def _vlsm_decision(vlsm: VLSMPlan) -> Decision:
    names = ", ".join(f"{block.name} {block.cidr}" for block in vlsm.blocks)
    reason = (
        f"Allocated {len(vlsm.blocks)} subnets inside {vlsm.root} by sorting host "
        f"requests largest-first and aligning each block to its own power-of-two "
        f"boundary. {vlsm.requested_total} requested hosts occupy "
        f"{vlsm.allocated_addresses} addresses ({vlsm.utilization:.1f}% address "
        f"utilisation, {vlsm.usable_utilization:.1f}% of usable addresses). "
        f"An independent range scan confirms no overlap. Plan: {names}."
    )
    return Decision(
        category="Addressing (VLSM)",
        choice=f"{vlsm.root} -> {len(vlsm.blocks)} non-overlapping subnets",
        reason=reason,
        standard="RFC 1918 private addressing; RFC 4632 CIDR; RFC 3021 for /31",
        severity="info",
        evidence={
            "root": vlsm.root,
            "blocks": len(vlsm.blocks),
            "requested_total": vlsm.requested_total,
            "allocated_addresses": vlsm.allocated_addresses,
            "utilization": round(vlsm.utilization, 2),
            "usable_utilization": round(vlsm.usable_utilization, 2),
            "wasted": vlsm.wasted,
        },
    )


def _security_decision(scenario: Scenario, plan_vlans: tuple[int, ...]) -> Decision:
    if scenario.cloud:
        choice = (
            "Guest/server ACL, SSH-only VTY, site-to-site IPsec on the cloud-facing "
            "interface, and a QoS priority queue for latency-sensitive traffic"
        )
        standard = "RFC 4301 (IPsec); Cisco IOS extended ACL syntax"
    else:
        choice = "Guest/server ACL, SSH-only VTY, and explicit trunk hardening"
        standard = "Cisco IOS extended ACL syntax; IEEE 802.1Q"
    return Decision(
        category="Security and hardening",
        choice=choice,
        reason=(
            "The Wi-Fi/guest subnet is denied reachability to the server subnet "
            "with an extended ACL, management access is restricted to SSH from the "
            "management subnet, and trunks use an explicit allowed-VLAN list with "
            "an unused native VLAN. "
            + (
                "The cloud boundary adds an ISAKMP/IPsec transform and crypto map "
                "because the traffic crosses an untrusted provider."
                if scenario.cloud
                else "No IPsec policy is generated because there is no cloud or WAN "
                "boundary in this scenario."
            )
        ),
        standard=standard,
        severity="info",
        evidence={
            "vlans": list(plan_vlans),
            "native_vlan": scenario.native_vlan,
            "ssh_only": True,
            "ipsec": scenario.cloud,
        },
    )


def design(
    scenario: Scenario,
    *,
    tier: str | None = None,
    routing_mode: str | None = None,
) -> Plan:
    """Run media -> VLSM -> topology -> routing -> switching."""
    media = tuple(select_media(link) for link in scenario.links)
    vlsm = allocate_vlsm(scenario.root_prefix, scenario.subnets)

    effective_tier = tier if tier is not None else scenario.forced_tier
    topology = plan_topology(scenario, effective_tier)
    routing = decide_routing(scenario, vlsm.blocks, routing_mode)
    switching = decide_switching(scenario, vlsm.blocks, topology)

    decisions: list[Decision] = []
    decisions.extend(_media_decisions(media))
    decisions.append(_vlsm_decision(vlsm))

    tier_severity = "violation" if topology.violation else "info"
    decisions.append(
        Decision(
            category="Topology",
            choice=(
                f"{topology.tier} ({topology.access_switches} access, "
                f"{topology.distribution_switches} distribution, "
                f"{topology.core_switches} core)"
            ),
            reason=topology.reason + " " + topology.cost_note,
            standard="CIC-307 topology-tier rule; 48-port access switch sizing",
            severity=tier_severity,
            evidence=topology.to_dict(),
        )
    )

    routing_severity = "violation" if routing.violation else "info"
    decisions.append(
        Decision(
            category="Routing (L3)",
            choice=routing.protocol,
            reason=routing.reason,
            standard="RFC 2328 (OSPFv2); RFC 4271 (BGP-4)",
            severity=routing_severity,
            evidence=routing.to_dict(),
        )
    )
    for summary in routing.summaries:
        decisions.append(
            Decision(
                category="Routing (L3)",
                choice=f"Area {summary.area} summary {summary.cidr}",
                reason=summary.reason,
                standard="RFC 2328 area range summarisation",
                severity="warning" if summary.exact else "info",
                evidence=summary.to_dict(),
            )
        )

    decisions.append(
        Decision(
            category="Switching (L2)",
            choice=f"{switching.stp} + {switching.fhrp}",
            reason=switching.reason,
            standard="IEEE 802.1w; IEEE 802.1s; RFC 5798 (VRRP alternative)",
            severity="info",
            evidence=switching.to_dict(),
        )
    )
    decisions.append(_security_decision(scenario, switching.allowed_vlans))

    violations: list[str] = []
    if topology.violation:
        violations.append(topology.violation)
    if routing.violation:
        violations.append(routing.violation)
    for item in media:
        if item.severity == "warning":
            violations.append(f"{item.link}: {item.reason}")

    return Plan(
        scenario=scenario,
        media=media,
        vlsm=vlsm,
        topology=topology,
        routing=routing,
        switching=switching,
        decisions=tuple(decisions),
        violations=tuple(violations),
        tier_override=effective_tier,
        routing_override=routing_mode,
    )


def _alternate_choices(selected: Plan) -> tuple[str, str]:
    tier = "collapsed-core" if selected.topology.tier == "Three-tier" else "three-tier"
    if selected.routing.bgp:
        routing_mode = "multi-area"
    elif selected.routing.multi_area:
        routing_mode = "area0"
    else:
        routing_mode = "multi-area"
    return tier, routing_mode


def analyze(scenario: Scenario) -> Analysis:
    """Return the selected design, an alternate, and copy-ready IOS."""
    from netarchitect.configs.configs import build_configs

    selected = design(scenario)
    alt_tier, alt_routing = _alternate_choices(selected)
    alternate = design(scenario, tier=alt_tier, routing_mode=alt_routing)

    device_configs, export_text = build_configs(selected)
    return Analysis(
        scenario=scenario,
        selected=selected,
        alternate=alternate,
        device_configs=device_configs,
        export_text=export_text,
        export_filename=f"{scenario.name}.txt",
    )


def safe_analyze(scenario: Scenario) -> tuple[Analysis | None, str | None]:
    """Dashboard helper: never raise into the HTML renderer."""
    try:
        return analyze(scenario), None
    except NetArchitectError as exc:
        return None, str(exc)
