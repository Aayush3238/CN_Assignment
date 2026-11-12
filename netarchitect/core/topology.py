"""Topology-tier sizing.

The rule from the specification and the reference report is mechanical:

* three-tier when ``endpoints >= 1000`` **or** ``buildings >= 4``;
* collapsed core otherwise;
* access switches = ``ceil(endpoints / 48)``;
* oversubscription = ``(48 x access speed) / (uplinks x uplink speed)``.

A forced collapsed core is recorded as a violation whenever the natural rule
would have chosen three-tier.  Cost is scored only when the scenario supplies
prices for all three switch roles; otherwise the plan says so explicitly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from netarchitect.core.spec import Scenario

THREE_TIER_ENDPOINTS = 1000
THREE_TIER_BUILDINGS = 4
HARD_COLLAPSED_ENDPOINTS = 5000
HARD_COLLAPSED_BUILDINGS = 6
ACCESS_PORTS_PER_SWITCH = 48


@dataclass(frozen=True)
class TopologyPlan:
    tier: str
    natural_tier: str
    access_switches: int
    distribution_switches: int
    core_switches: int
    oversubscription: float
    ratio: str
    violation: str | None
    reason: str
    advantages: tuple[str, ...]
    disadvantages: tuple[str, ...]
    tradeoffs: tuple[str, ...]
    cost: float | None = None
    cost_note: str = ""

    @property
    def switch_count(self) -> int:
        return self.access_switches + self.distribution_switches + self.core_switches

    def to_dict(self) -> dict[str, object]:
        return {
            "tier": self.tier,
            "natural_tier": self.natural_tier,
            "access_switches": self.access_switches,
            "distribution_switches": self.distribution_switches,
            "core_switches": self.core_switches,
            "switch_count": self.switch_count,
            "oversubscription": round(self.oversubscription, 3),
            "ratio": self.ratio,
            "violation": self.violation,
            "reason": self.reason,
            "advantages": list(self.advantages),
            "disadvantages": list(self.disadvantages),
            "tradeoffs": list(self.tradeoffs),
            "cost": self.cost,
            "cost_note": self.cost_note,
        }


def natural_tier(scenario: Scenario) -> str:
    if scenario.endpoints >= THREE_TIER_ENDPOINTS or scenario.buildings >= THREE_TIER_BUILDINGS:
        return "Three-tier"
    return "Collapsed core"


def plan_topology(scenario: Scenario, tier: str | None = None) -> TopologyPlan:
    """Size the topology, optionally overriding the natural tier."""
    natural = natural_tier(scenario)
    selected = natural
    if tier is not None:
        normalised = tier.lower().replace("_", "-")
        if normalised in {"three-tier", "threetier", "3-tier"}:
            selected = "Three-tier"
        elif normalised in {"collapsed", "collapsed-core", "collapsedcore"}:
            selected = "Collapsed core"
        else:
            raise ValueError(f"unknown topology tier: {tier!r}")

    access_switches = math.ceil(scenario.endpoints / ACCESS_PORTS_PER_SWITCH)
    cores = 2 if scenario.resilient else 1

    if selected == "Three-tier":
        distribution_switches = max(1, scenario.buildings)
        core_switches = cores
        advantages = (
            "Fault domains and broadcast domains stay small.",
            "Distribution switches summarise routes and enforce policy.",
            "Core links can be sized and upgraded independently.",
        )
        disadvantages = (
            "More switches and more cabling than a collapsed core.",
            "More OSPF adjacencies and more configuration surface.",
        )
        tradeoffs = (
            "Higher capital cost; cleaner growth path and predictable convergence.",
        )
    else:
        distribution_switches = 0
        core_switches = cores
        advantages = (
            "Fewer devices and lower capital cost.",
            "Short, simple Layer-2 domains for a small site.",
        )
        disadvantages = (
            "Core and distribution functions share the same chassis.",
            "Growth past the tier threshold forces a redesign, not an upgrade.",
        )
        tradeoffs = (
            "Lower cost now; limited scale and a single policy boundary.",
        )

    access_speed = scenario.access_speed_gbps
    uplink_speed = scenario.uplink_speed_gbps
    uplinks = scenario.uplinks
    oversubscription = (ACCESS_PORTS_PER_SWITCH * access_speed) / (uplinks * uplink_speed)
    ratio = f"{oversubscription:.1f}:1"

    if selected == "Three-tier":
        reason = (
            f"Selected three-tier because endpoints ({scenario.endpoints}) are "
            f">= {THREE_TIER_ENDPOINTS} or buildings ({scenario.buildings}) are "
            f">= {THREE_TIER_BUILDINGS}. The design uses {access_switches} access "
            f"switch(es) at {ACCESS_PORTS_PER_SWITCH} ports each, "
            f"{distribution_switches} distribution switch(es), and {core_switches} "
            f"core switch(es). Oversubscription is (48 x {access_speed} Gb/s) / "
            f"({uplinks} x {uplink_speed} Gb/s) = {ratio}."
        )
    else:
        reason = (
            f"Selected a collapsed core because endpoints ({scenario.endpoints}) "
            f"are < {THREE_TIER_ENDPOINTS} and buildings ({scenario.buildings}) are "
            f"< {THREE_TIER_BUILDINGS}. The design uses {access_switches} access "
            f"switch(es) and {core_switches} combined core/distribution switch(es). "
            f"Oversubscription is (48 x {access_speed} Gb/s) / "
            f"({uplinks} x {uplink_speed} Gb/s) = {ratio}."
        )

    violation: str | None = None
    if selected == "Collapsed core" and natural == "Three-tier":
        violation = (
            f"Collapsed core violates the tier rule for {scenario.endpoints} "
            f"endpoints and {scenario.buildings} buildings; three-tier is required "
            f"at >= {THREE_TIER_ENDPOINTS} endpoints or >= {THREE_TIER_BUILDINGS} buildings."
        )
        if scenario.endpoints >= HARD_COLLAPSED_ENDPOINTS or scenario.buildings >= HARD_COLLAPSED_BUILDINGS:
            violation += (
                f" This also breaches the hard limit of {HARD_COLLAPSED_ENDPOINTS} "
                f"endpoints / {HARD_COLLAPSED_BUILDINGS} buildings for a collapsed core."
            )

    cost: float | None = None
    cost_note = "Cost was not scored because the scenario did not supply all three switch prices."
    if scenario.prices:
        cost = (
            access_switches * scenario.prices["access"]
            + distribution_switches * scenario.prices["distribution"]
            + core_switches * scenario.prices["core"]
        )
        cost_note = (
            f"Cost scored from supplied prices: {access_switches} access x "
            f"{scenario.prices['access']:.0f} + {distribution_switches} distribution x "
            f"{scenario.prices['distribution']:.0f} + {core_switches} core x "
            f"{scenario.prices['core']:.0f} = {cost:.0f}."
        )

    return TopologyPlan(
        tier=selected,
        natural_tier=natural,
        access_switches=access_switches,
        distribution_switches=distribution_switches,
        core_switches=core_switches,
        oversubscription=oversubscription,
        ratio=ratio,
        violation=violation,
        reason=reason,
        advantages=advantages,
        disadvantages=disadvantages,
        tradeoffs=tradeoffs,
        cost=cost,
        cost_note=cost_note,
    )
