"""Pydantic data models shared by every layer of the application.

These models serve three purposes:
1. Validate user input (JSON files) before the rule engine touches it.
2. Carry structured output between the engine, reports, storage, and configs.
3. Document the shape of a run so it can be serialized to JSON/SQLite losslessly.
"""

from __future__ import annotations

import ipaddress
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Cisco reserves these VLAN IDs; the design also reserves 999 as an unused
# native VLAN to reduce VLAN-hopping risk.
RESERVED_VLAN_IDS = {0, 1, 1002, 1003, 1004, 1005}
NATIVE_VLAN_ID = 999


class VLANRequest(BaseModel):
    """One broadcast domain requested by the user.

    ``hosts`` is the number of usable hosts required, not the raw block size.
    The VLSM allocator adds network/broadcast addresses when sizing the subnet.
    """

    name: str = Field(min_length=1, description="Human readable VLAN name")
    hosts: int = Field(ge=1, description="Required usable host addresses")
    purpose: str = ""
    poe: bool = False
    vlan_id: int | None = Field(default=None, ge=1, le=4094)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        # Strip surrounding whitespace so " Staff " and "Staff" are the same.
        value = value.strip()
        if not value:
            raise ValueError("VLAN name cannot be blank")
        return value

    @field_validator("vlan_id")
    @classmethod
    def _validate_vlan_id(cls, value: int | None) -> int | None:
        # Fail early for IDs that IOS reserves or that the design reserves as
        # the untagged native VLAN.
        if value is None:
            return None
        if value in RESERVED_VLAN_IDS or value == NATIVE_VLAN_ID:
            raise ValueError(f"VLAN ID {value} is reserved")
        return value


class LinkSpec(BaseModel):
    """A physical link the media engine must select hardware for."""

    name: str
    distance_m: float = Field(gt=0, description="Cable run length in metres")
    category: Literal["access", "backbone", "wan"]
    service: Literal["dark-fiber", "internet"] = "dark-fiber"
    requested_media: Literal["auto", "copper", "mmf", "smf"] = "auto"


class ScenarioInput(BaseModel):
    """Validated input for one network design scenario."""

    profile: str = Field(min_length=1)
    description: str = ""
    buildings: int = Field(default=0, ge=0)
    remote_sites: int = Field(default=0, ge=0)
    endpoints: int = Field(gt=0, description="Total endpoint/device count")
    access_distance_m: float = Field(default=90, gt=0)
    backbone_distance_m: float = Field(default=0, ge=0)
    wan_distance_m: float = Field(default=0, ge=0)
    wan_service: Literal["dark-fiber", "internet"] = "dark-fiber"
    uplink_gbps: float = Field(default=10, gt=0)
    poe_aps: int = Field(default=0, ge=0)
    resiliency: Literal["single-homed", "dual-homed", "dual-uplink"] = "single-homed"
    cloud_vpc: bool = False
    qos_latency_ms: float | None = Field(default=None, gt=0)
    root_prefix: str = "10.0.0.0/16"
    vlans: list[VLANRequest] = Field(min_length=1)

    @field_validator("root_prefix")
    @classmethod
    def _validate_root_prefix(cls, value: str) -> str:
        # ``strict=False`` lets users type 10.0.0.0/16 even if they meant the
        # network address; non-network addresses are normalised below.
        try:
            network = ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError(f"invalid IPv4 prefix: {value}") from exc
        if network.version != 4:
            raise ValueError("only IPv4 prefixes are supported")
        if network.prefixlen > 29:
            raise ValueError("root prefix must be /29 or larger (need at least two hosts)")
        return str(network)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "ScenarioInput":
        names = [vlan.name.lower() for vlan in self.vlans]
        if len(names) != len(set(names)):
            raise ValueError("VLAN names must be unique")

        # Explicit VLAN IDs may collide with each other.
        ids = [vlan.vlan_id for vlan in self.vlans if vlan.vlan_id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("explicit VLAN IDs must be unique")

        # Catch an obviously inconsistent scenario early: requesting more hosts
        # across VLANs than the declared endpoint count is almost always a typo.
        requested_hosts = sum(vlan.hosts for vlan in self.vlans)
        if requested_hosts > self.endpoints:
            raise ValueError(
                f"VLAN host requests ({requested_hosts}) exceed declared "
                f"endpoints ({self.endpoints})"
            )
        return self

    def links(self) -> list[LinkSpec]:
        """Expand the scenario into the physical links that need media choices.

        Access is always present. Backbone and WAN links are only included when
        the scenario supplies a non-zero distance. For internet WANs the service
        type is passed through so the media engine can select an ISP handoff
        instead of trying to buy 5,000 km of dark fiber.
        """
        links = [
            LinkSpec(
                name="LAN access",
                distance_m=self.access_distance_m,
                category="access",
            )
        ]
        if self.backbone_distance_m > 0:
            links.append(
                LinkSpec(
                    name="Building/site backbone",
                    distance_m=self.backbone_distance_m,
                    category="backbone",
                )
            )
        if self.wan_distance_m > 0:
            links.append(
                LinkSpec(
                    name="WAN/MAN link",
                    distance_m=self.wan_distance_m,
                    category="wan",
                    service=self.wan_service,
                )
            )
        return links


class MediaRecommendation(BaseModel):
    """One L1 media/transceiver decision with its engineering justification."""

    link: str
    distance_m: float
    category: str
    media: str
    transceiver: str
    standard: str
    rationale: str
    rule_id: str


class Subnet(BaseModel):
    """A single VLSM allocation result."""

    name: str
    requested_hosts: int
    cidr: str
    network: str
    netmask: str
    wildcard: str
    broadcast: str
    first_host: str | None
    last_host: str | None
    gateway: str | None
    usable_hosts: int
    point_to_point: bool = False


class Utilization(BaseModel):
    """Address-space utilisation metrics for the VLSM plan."""

    root_prefix: str
    root_addresses: int
    allocated_addresses: int
    address_pct: float
    requested_hosts: int
    usable_hosts: int
    host_pct: float


class VLSMAllocation(BaseModel):
    subnets: list[Subnet]
    utilization: Utilization


class VLANPlan(BaseModel):
    """An 802.1Q VLAN and its associated SVI/subnet."""

    vlan_id: int
    name: str
    purpose: str
    subnet: str | None
    gateway: str | None
    trunk_allowed: list[int]
    native_vlan: int
    rstp_role: str
    poe: bool
    rationale: str


class RoutingDecision(BaseModel):
    """Selected L3 routing protocol plus area/route-summary plan."""

    protocol: str
    areas: dict[str, list[str]]
    rationale: str
    rule_id: str
    summarization: list[str]


class Rationale(BaseModel):
    """A machine-readable explanation record produced by the rule engine."""

    rule_id: str
    domain: str
    inputs: dict
    condition: str
    choice: str
    rationale: str
    standard: str = ""


class RunResult(BaseModel):
    """Everything produced by one engine run.

    This object is what gets rendered by the CLI and stored in SQLite, so it is
    intentionally self-contained (input + all decisions + configs).
    """

    scenario: ScenarioInput
    media: list[MediaRecommendation]
    vlans: list[VLANPlan]
    routing: RoutingDecision
    subnets: list[Subnet]
    utilization: Utilization
    rationales: list[Rationale]
    configs: dict[str, str]
