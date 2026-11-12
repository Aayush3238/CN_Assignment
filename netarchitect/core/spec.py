"""Scenario ingestion and validation.

A scenario is a plain JSON object.  Presets and user-supplied files flow
through exactly the same parser, so a preset cannot use a shortcut a custom
file could not use.

Validation is intentionally strict:

* a boolean is never accepted where an integer is required (``bool`` is a
  subclass of ``int`` in Python, which hides a common JSON type error);
* distances are numbers greater than zero and are never clamped;
* a subnet may belong to only one site;
* a pricing block must contain all three switch prices;
* reserved VLAN ids (1, 999, 1002-1005) cannot be assigned to a user VLAN.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable

from netarchitect.core.errors import InvalidParameterError
from netarchitect.core.ipv4 import format_cidr, parse_cidr

PRESET_DIR = Path(__file__).resolve().parent.parent / "presets"
PRESET_ALIASES = {
    "campus": "campus",
    "campus-lan": "campus",
    "metro": "metro",
    "metro-man": "metro",
    "wan": "wan",
    "global-wan": "wan",
}
PRESET_NAMES = ("campus", "metro", "wan")

RESERVED_VLAN_IDS = {1, 999, 1002, 1003, 1004, 1005}
P2P_MODES = {"p2p30", "p2p31", "p2p32"}


def _fail(message: str) -> None:
    raise InvalidParameterError(message)


def _mapping(value: object, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{where} must be a JSON object")
    return value


def _text(data: dict[str, Any], key: str, where: str, *, default: str | None = None) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        _fail(f"{where}.{key} must be a non-blank string")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str, where: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _fail(f"{where}.{key} must be a string when supplied")
    return value.strip()


def _integer(
    data: dict[str, Any],
    key: str,
    where: str,
    *,
    minimum: int = 1,
    maximum: int | None = None,
    default: int | None = None,
    required: bool = True,
) -> int:
    if key not in data or data[key] is None:
        if required:
            _fail(f"{where}.{key} is required")
        assert default is not None
        return default
    value = data[key]
    # bool is a subclass of int: reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"{where}.{key} must be an integer, got {type(value).__name__}")
    if value < minimum:
        _fail(f"{where}.{key} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        _fail(f"{where}.{key} must be <= {maximum}, got {value}")
    return value


def _number(
    data: dict[str, Any],
    key: str,
    where: str,
    *,
    minimum: float = 0.0,
    maximum: float | None = None,
    required: bool = True,
    default: float | None = None,
) -> float:
    if key not in data or data[key] is None:
        if required:
            _fail(f"{where}.{key} is required")
        assert default is not None
        return default
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(f"{where}.{key} must be numeric, got {type(value).__name__}")
    number = float(value)
    if number < minimum:
        _fail(f"{where}.{key} must be >= {minimum:g}, got {number:g}")
    if maximum is not None and number > maximum:
        _fail(f"{where}.{key} must be <= {maximum:g}, got {number:g}")
    return number


def _boolean(
    data: dict[str, Any], key: str, where: str, *, required: bool = True, default: bool = False
) -> bool:
    if key not in data or data[key] is None:
        if required:
            _fail(f"{where}.{key} is required")
        return default
    value = data[key]
    if not isinstance(value, bool):
        _fail(f"{where}.{key} must be true or false, got {type(value).__name__}")
    return value


@dataclass(frozen=True)
class Link:
    name: str
    distance_m: float
    kind: str = "backbone"  # access | backbone | wan
    media: str = "auto"  # auto | copper | fiber
    connectors: int = 2
    splices: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "distance_m": self.distance_m,
            "kind": self.kind,
            "media": self.media,
            "connectors": self.connectors,
            "splices": self.splices,
        }


@dataclass(frozen=True)
class SubnetRequest:
    name: str
    hosts: int
    vlan: int | None = None
    mode: str = "lan"  # lan | p2p30 | p2p31
    site: str | None = None
    poe: bool = False
    between: tuple[str, str] | None = None

    @property
    def point_to_point(self) -> bool:
        return self.mode in P2P_MODES

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "hosts": self.hosts,
            "mode": self.mode,
            "poe": self.poe,
        }
        if self.vlan is not None:
            payload["vlan"] = self.vlan
        if self.site is not None:
            payload["site"] = self.site
        if self.between is not None:
            payload["between"] = list(self.between)
        return payload


@dataclass(frozen=True)
class Site:
    name: str
    subnets: tuple[str, ...]
    role: str = "site"

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "subnets": list(self.subnets), "role": self.role}


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    endpoints: int
    buildings: int
    links: tuple[Link, ...]
    root_prefix: str
    subnets: tuple[SubnetRequest, ...]
    sites: tuple[Site, ...]
    resilient: bool
    single_as: bool
    cloud: bool
    local_asn: int | None
    peer_asn: int | None
    access_speed_gbps: int
    uplink_speed_gbps: int
    uplinks: int
    forced_tier: str | None = None
    prices: dict[str, float] | None = None
    native_vlan: int = 999

    def link(self, kind: str) -> Link | None:
        for item in self.links:
            if item.kind == kind:
                return item
        return None

    def subnet(self, name: str) -> SubnetRequest | None:
        for item in self.subnets:
            if item.name.lower() == name.lower():
                return item
        return None

    def site_of(self, subnet_name: str) -> str | None:
        for site in self.sites:
            for name in site.subnets:
                if name.lower() == subnet_name.lower():
                    return site.name
        return None

    def with_overrides(
        self,
        *,
        endpoints: int | None = None,
        buildings: int | None = None,
        distance_m: float | None = None,
        resilient: bool | None = None,
    ) -> "Scenario":
        """Return a copy with dashboard form overrides applied.

        The overrides are re-validated through the same helpers so a crafted
        query string cannot put a boolean into an integer field.
        """
        payload = self.to_dict()
        if endpoints is not None:
            payload["endpoints"] = endpoints
        if buildings is not None:
            payload["buildings"] = buildings
        if resilient is not None:
            payload["resilient"] = resilient
        if distance_m is not None:
            links = payload["links"]
            replaced = False
            for link in links:
                if link["kind"] == "backbone":
                    link["distance_m"] = distance_m
                    replaced = True
                    break
            if not replaced and links:
                links[0]["distance_m"] = distance_m
        return Scenario.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "endpoints": self.endpoints,
            "buildings": self.buildings,
            "links": [link.to_dict() for link in self.links],
            "root_prefix": self.root_prefix,
            "subnets": [subnet.to_dict() for subnet in self.subnets],
            "sites": [site.to_dict() for site in self.sites],
            "resilient": self.resilient,
            "single_as": self.single_as,
            "cloud": self.cloud,
            "local_asn": self.local_asn,
            "peer_asn": self.peer_asn,
            "access_speed_gbps": self.access_speed_gbps,
            "uplink_speed_gbps": self.uplink_speed_gbps,
            "uplinks": self.uplinks,
            "forced_tier": self.forced_tier,
            "prices": self.prices,
            "native_vlan": self.native_vlan,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "Scenario":
        data = _mapping(payload, "scenario")
        name = _text(data, "name", "scenario")
        description = _optional_text(data, "description", "scenario") or ""
        endpoints = _integer(data, "endpoints", "scenario", minimum=1, maximum=1_000_000)
        buildings = _integer(data, "buildings", "scenario", minimum=1, maximum=1_000)

        links_raw = data.get("links")
        if not isinstance(links_raw, list) or not links_raw:
            _fail("scenario.links must be a non-empty array")
        links: list[Link] = []
        for index, raw in enumerate(links_raw):
            where = f"scenario.links[{index}]"
            item = _mapping(raw, where)
            link_name = _text(item, "name", where)
            distance = _number(item, "distance_m", where, minimum=0.000001, maximum=20_000_000)
            kind = _text(item, "kind", where, default="backbone").lower()
            if kind not in {"access", "backbone", "wan"}:
                _fail(f"{where}.kind must be access, backbone, or wan")
            media = _text(item, "media", where, default="auto").lower()
            if media not in {"auto", "copper", "fiber"}:
                _fail(f"{where}.media must be auto, copper, or fiber")
            connectors = _integer(item, "connectors", where, minimum=0, maximum=20, default=2, required=False)
            splices = _integer(item, "splices", where, minimum=0, maximum=100, default=0, required=False)
            links.append(
                Link(link_name, distance, kind, media, connectors, splices)
            )

        root_text = _text(data, "root_prefix", "scenario")
        try:
            root_network, root_prefix = parse_cidr(root_text)
        except ValueError as exc:
            _fail(f"scenario.root_prefix is invalid: {exc}")

        subnets_raw = data.get("subnets")
        if not isinstance(subnets_raw, list) or not subnets_raw:
            _fail("scenario.subnets must be a non-empty array")
        subnets: list[SubnetRequest] = []
        seen_names: set[str] = set()
        seen_vlans: set[int] = set()
        for index, raw in enumerate(subnets_raw):
            where = f"scenario.subnets[{index}]"
            item = _mapping(raw, where)
            subnet_name = _text(item, "name", where)
            key = subnet_name.lower()
            if key in seen_names:
                _fail(f"{where}.name duplicates another subnet: {subnet_name!r}")
            seen_names.add(key)
            hosts = _integer(item, "hosts", where, minimum=1, maximum=1_000_000)
            mode = _text(item, "mode", where, default="lan").lower()
            if mode not in {"lan", "p2p30", "p2p31", "p2p32"}:
                _fail(f"{where}.mode must be lan, p2p30, p2p31, or p2p32")
            vlan: int | None = None
            if item.get("vlan") is not None:
                vlan = _integer(item, "vlan", where, minimum=2, maximum=4094)
                if vlan in RESERVED_VLAN_IDS:
                    _fail(f"{where}.vlan {vlan} is reserved and cannot carry user traffic")
                if vlan in seen_vlans:
                    _fail(f"{where}.vlan {vlan} is already assigned")
                seen_vlans.add(vlan)
            if mode != "lan" and vlan is not None:
                _fail(f"{where} is point-to-point and cannot also have a VLAN")
            poe = _boolean(item, "poe", where, required=False, default=False)
            site = _optional_text(item, "site", where)
            between: tuple[str, str] | None = None
            if item.get("between") is not None:
                raw_between = item["between"]
                if not isinstance(raw_between, list) or len(raw_between) != 2:
                    _fail(f"{where}.between must be an array of two endpoint names")
                first, second = raw_between
                if not isinstance(first, str) or not isinstance(second, str):
                    _fail(f"{where}.between must contain strings")
                if not first.strip() or not second.strip():
                    _fail(f"{where}.between names must be non-blank")
                between = (first.strip(), second.strip())
            if mode in P2P_MODES and between is None:
                _fail(f"{where} is point-to-point and requires a between pair")
            subnets.append(SubnetRequest(subnet_name, hosts, vlan, mode, site, poe, between))

        if sum(item.hosts for item in subnets) > endpoints * 2:
            _fail(
                "scenario density is implausible: subnet host requests exceed "
                f"twice the endpoint count ({endpoints})"
            )

        resilient = _boolean(data, "resilient", "scenario")
        single_as = _boolean(data, "single_as", "scenario", required=False, default=True)
        cloud = _boolean(data, "cloud", "scenario", required=False, default=False)

        local_asn: int | None = None
        peer_asn: int | None = None
        if data.get("local_asn") is not None:
            local_asn = _integer(data, "local_asn", "scenario", minimum=1, maximum=4_294_967_295)
        if data.get("peer_asn") is not None:
            peer_asn = _integer(data, "peer_asn", "scenario", minimum=1, maximum=4_294_967_295)

        access_speed = _integer(data, "access_speed_gbps", "scenario", minimum=1, maximum=400)
        uplink_speed = _integer(data, "uplink_speed_gbps", "scenario", minimum=1, maximum=400)
        uplinks = _integer(data, "uplinks", "scenario", minimum=1, maximum=32)

        forced_tier = _optional_text(data, "forced_tier", "scenario")
        if forced_tier is not None:
            forced_tier = forced_tier.lower().replace("_", "-")
            if forced_tier in {"three-tier", "threetier", "3-tier"}:
                forced_tier = "three-tier"
            elif forced_tier in {"collapsed", "collapsed-core", "collapsedcore"}:
                forced_tier = "collapsed-core"
            else:
                _fail("scenario.forced_tier must be three-tier or collapsed-core")

        prices: dict[str, float] | None = None
        if data.get("prices") is not None:
            price_data = _mapping(data["prices"], "scenario.prices")
            missing = [key for key in ("access", "distribution", "core") if key not in price_data]
            if missing:
                _fail(
                    "scenario.prices must include access, distribution, and core "
                    f"(missing {', '.join(missing)})"
                )
            prices = {
                key: _number(price_data, key, "scenario.prices", minimum=0)
                for key in ("access", "distribution", "core")
            }

        sites_raw = data.get("sites")
        sites: list[Site] = []
        if sites_raw is not None:
            if not isinstance(sites_raw, list) or not sites_raw:
                _fail("scenario.sites must be a non-empty array when supplied")
            seen_sites: set[str] = set()
            claimed: dict[str, str] = {}
            for index, raw in enumerate(sites_raw):
                where = f"scenario.sites[{index}]"
                item = _mapping(raw, where)
                site_name = _text(item, "name", where)
                if site_name.lower() in seen_sites:
                    _fail(f"{where}.name duplicates another site: {site_name!r}")
                seen_sites.add(site_name.lower())
                raw_subnets = item.get("subnets")
                if not isinstance(raw_subnets, list) or not raw_subnets:
                    _fail(f"{where}.subnets must be a non-empty array")
                names: list[str] = []
                for raw_name in raw_subnets:
                    if not isinstance(raw_name, str) or not raw_name.strip():
                        _fail(f"{where}.subnets must contain non-blank strings")
                    subnet_name = raw_name.strip()
                    if subnet_name.lower() not in seen_names:
                        _fail(f"{where} references unknown subnet {subnet_name!r}")
                    owner = claimed.get(subnet_name.lower())
                    if owner is not None:
                        _fail(
                            f"subnet {subnet_name!r} is claimed by both {owner!r} "
                            f"and {site_name!r}"
                        )
                    claimed[subnet_name.lower()] = site_name
                    names.append(subnet_name)
                role = _text(item, "role", where, default="site").lower()
                sites.append(Site(site_name, tuple(names), role))

            unclaimed = [item.name for item in subnets if item.name.lower() not in claimed]
            if unclaimed:
                sites.append(Site("Core", tuple(unclaimed), "core"))
        else:
            sites.append(Site("Core", tuple(item.name for item in subnets), "core"))

        native_vlan = _integer(
            data, "native_vlan", "scenario", minimum=2, maximum=4094, default=999, required=False
        )
        if native_vlan in seen_vlans:
            _fail("scenario.native_vlan must not be an assigned user VLAN")

        return cls(
            name=name,
            description=description,
            endpoints=endpoints,
            buildings=buildings,
            links=tuple(links),
            root_prefix=format_cidr(root_network, root_prefix),
            subnets=tuple(subnets),
            sites=tuple(sites),
            resilient=resilient,
            single_as=single_as,
            cloud=cloud,
            local_asn=local_asn,
            peer_asn=peer_asn,
            access_speed_gbps=access_speed,
            uplink_speed_gbps=uplink_speed,
            uplinks=uplinks,
            forced_tier=forced_tier,
            prices=prices,
            native_vlan=native_vlan,
        )


def load_preset(name: str) -> Scenario:
    """Load one of the three built-in presets by short or long name."""
    key = PRESET_ALIASES.get(name.strip().lower())
    if key is None:
        available = ", ".join(PRESET_NAMES)
        _fail(f"unknown preset {name!r}; choose one of {available}")
    path = PRESET_DIR / f"{key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:  # pragma: no cover - packaging error
        _fail(f"preset file missing: {path}")
    return Scenario.from_dict(payload)


def load_scenario_file(path: str | Path) -> Scenario:
    """Read and validate a custom scenario JSON file."""
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail(f"scenario file not found: {target}")
    except json.JSONDecodeError as exc:
        _fail(f"scenario file is not valid JSON: {exc}")
    return Scenario.from_dict(payload)


def all_presets() -> dict[str, Scenario]:
    return {name: load_preset(name) for name in PRESET_NAMES}


def scenario_names(scenarios: Iterable[Scenario]) -> list[str]:
    return [item.name for item in scenarios]


def clone_with(scenario: Scenario, **changes: Any) -> Scenario:
    """Typed wrapper around :func:`dataclasses.replace` for small edits."""
    return replace(scenario, **changes)
