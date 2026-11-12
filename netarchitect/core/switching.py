"""Layer-2 control-plane choices: spanning tree, FHRP, and trunk hardening.

RSTP (IEEE 802.1w) is selected when the plan has at most 16 VLANs and fewer
than 50 switches.  Above either limit the decision is MSTP (IEEE 802.1s).
HSRP is generated when the scenario is resilient; VRRP (RFC 5798) is named as
the vendor-neutral alternative.

Trunks always carry an explicit allowed-VLAN list, never ``allowed vlan all``,
and the native VLAN is an unused id (999 by default).
"""

from __future__ import annotations

from dataclasses import dataclass

from netarchitect.core.spec import Scenario
from netarchitect.core.topology import TopologyPlan
from netarchitect.core.vlsm import SubnetBlock

RSTP_VLAN_LIMIT = 16
RSTP_SWITCH_LIMIT = 50


@dataclass(frozen=True)
class SwitchingPlan:
    stp: str
    stp_mode: str
    fhrp: str
    fhrp_alternative: str
    vlan_count: int
    switch_count: int
    native_vlan: int
    allowed_vlans: tuple[int, ...]
    reason: str
    hardening: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "stp": self.stp,
            "stp_mode": self.stp_mode,
            "fhrp": self.fhrp,
            "fhrp_alternative": self.fhrp_alternative,
            "vlan_count": self.vlan_count,
            "switch_count": self.switch_count,
            "native_vlan": self.native_vlan,
            "allowed_vlans": list(self.allowed_vlans),
            "reason": self.reason,
            "hardening": list(self.hardening),
        }


def decide_switching(
    scenario: Scenario,
    blocks: tuple[SubnetBlock, ...] | list[SubnetBlock],
    topology: TopologyPlan,
) -> SwitchingPlan:
    vlan_count = sum(1 for block in blocks if block.vlan is not None)
    switch_count = topology.switch_count
    if vlan_count <= RSTP_VLAN_LIMIT and switch_count < RSTP_SWITCH_LIMIT:
        stp = "RSTP"
        stp_mode = "rapid-pvst"
        stp_reason = (
            f"RSTP (IEEE 802.1w) is sufficient: {vlan_count} VLAN(s) <= "
            f"{RSTP_VLAN_LIMIT} and {switch_count} switch(es) < {RSTP_SWITCH_LIMIT}. "
            "Rapid PVST+ gives sub-second convergence per VLAN and Packet Tracer "
            "accepts it directly."
        )
    else:
        stp = "MSTP"
        stp_mode = "mst"
        stp_reason = (
            f"MSTP (IEEE 802.1s) is required: {vlan_count} VLAN(s) or "
            f"{switch_count} switch(es) exceed the RSTP design limit "
            f"({RSTP_VLAN_LIMIT} VLANs / {RSTP_SWITCH_LIMIT} switches). MSTP maps "
            "many VLANs to a few instances and bounds the spanning-tree state."
        )

    if scenario.resilient:
        fhrp = "HSRP"
        fhrp_reason = (
            "HSRP is configured because the scenario is resilient: two cores share "
            "a virtual gateway, the first core uses priority 110, the second 100, "
            "and preemption returns traffic after a failure. VRRP (RFC 5798) is "
            "the open alternative."
        )
    else:
        fhrp = "None"
        fhrp_reason = (
            "No first-hop redundancy protocol is generated because the scenario is "
            "not resilient. VRRP (RFC 5798) or HSRP would be added for a dual-core "
            "design."
        )

    allowed = tuple(sorted(block.vlan for block in blocks if block.vlan is not None))
    hardening = (
        "Every trunk lists allowed VLAN ids explicitly; 'switchport trunk allowed vlan all' is never emitted.",
        f"Native VLAN is {scenario.native_vlan} and is not in the allowed user list.",
        "Access ports enable PortFast and BPDU Guard.",
        "Management VTY lines accept SSH only and are filtered by an ACL.",
    )

    reason = f"{stp_reason} {fhrp_reason} Trunk hardening: allowed VLANs {', '.join(map(str, allowed)) or 'none'}, native VLAN {scenario.native_vlan}."

    return SwitchingPlan(
        stp=stp,
        stp_mode=stp_mode,
        fhrp=fhrp,
        fhrp_alternative="VRRP (RFC 5798)",
        vlan_count=vlan_count,
        switch_count=switch_count,
        native_vlan=scenario.native_vlan,
        allowed_vlans=allowed,
        reason=reason,
        hardening=hardening,
    )
