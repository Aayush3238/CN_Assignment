"""Layer-2 VLAN / RSTP / PoE planning.

The planner deliberately avoids the common "allow all VLANs on every trunk"
mistake: trunk allowed lists are explicit and an unused native VLAN (999) is
reserved to reduce VLAN-hopping exposure.
"""

from __future__ import annotations

from netarchitect.core.models import (
    NATIVE_VLAN_ID,
    RESERVED_VLAN_IDS,
    ScenarioInput,
    Subnet,
    VLANPlan,
    VLANRequest,
)


def _is_management(name: str) -> bool:
    lowered = name.lower()
    return "mgmt" in lowered or "management" in lowered


def build_vlan_plan(
    scenario: ScenarioInput,
    subnets: list[Subnet],
) -> list[VLANPlan]:
    """Map every VLAN request to an ID, subnet, gateway, and trunk policy.

    Raises:
        ValueError: for reserved/duplicate VLAN IDs.
    """
    by_name = {subnet.name: subnet for subnet in subnets}
    used_ids: set[int] = set()
    next_id = 10

    # First pass: resolve every VLAN ID before building plans so the trunk
    # allowed list and RSTP root are consistent across all entries.
    assignments: list[tuple[int, VLANRequest]] = []
    for request in scenario.vlans:
        vlan_id = request.vlan_id
        if vlan_id is None:
            while (
                next_id in used_ids
                or next_id in RESERVED_VLAN_IDS
                or next_id == NATIVE_VLAN_ID
            ):
                next_id += 1
            vlan_id = next_id
            next_id += 1

        if vlan_id in RESERVED_VLAN_IDS or vlan_id == NATIVE_VLAN_ID:
            raise ValueError(
                f"VLAN ID {vlan_id} is reserved and cannot be used for '{request.name}'"
            )
        if vlan_id in used_ids:
            raise ValueError(f"duplicate VLAN ID {vlan_id}")

        used_ids.add(vlan_id)
        assignments.append((vlan_id, request))

    allowed_vlans = sorted(used_ids | {NATIVE_VLAN_ID})

    # Pick a management VLAN as the RSTP root where possible; otherwise the
    # first user VLAN becomes the root bridge for deterministic behaviour.
    root_request = next(
        (request for _, request in assignments if _is_management(request.name)),
        assignments[0][1],
    )
    root_id = next(
        vlan_id for vlan_id, request in assignments if request is root_request
    )

    plans: list[VLANPlan] = []
    for vlan_id, request in assignments:
        subnet = by_name.get(request.name)
        role = "root (priority 4096)" if vlan_id == root_id else "designated"
        purpose = request.purpose or "general access"

        rationale = (
            f"VLAN {vlan_id} ({request.name}) carries {purpose} on "
            f"{subnet.cidr if subnet else 'an unallocated subnet'} with gateway "
            f"{subnet.gateway if subnet else 'n/a'}. Trunks permit only VLANs "
            f"{', '.join(str(v) for v in allowed_vlans)}; native VLAN "
            f"{NATIVE_VLAN_ID} is reserved and unused to prevent double-tagged "
            f"VLAN hopping. RSTP role: {role}."
        )
        if request.poe:
            rationale += (
                " PoE is enabled on access ports for this VLAN (802.3af/at budget "
                "planned per AP)."
            )

        plans.append(
            VLANPlan(
                vlan_id=vlan_id,
                name=request.name,
                purpose=purpose,
                subnet=subnet.cidr if subnet else None,
                gateway=subnet.gateway if subnet else None,
                trunk_allowed=allowed_vlans,
                native_vlan=NATIVE_VLAN_ID,
                rstp_role=role,
                poe=request.poe,
                rationale=rationale,
            )
        )

    return plans
