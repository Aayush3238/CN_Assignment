"""Test helpers: a small valid scenario that can be mutated per test."""

from __future__ import annotations

from netarchitect.core.spec import Scenario


def scenario_dict(**overrides):
    payload = {
        "name": "test",
        "description": "Unit-test scenario",
        "endpoints": 120,
        "buildings": 1,
        "links": [{"name": "LAN access", "distance_m": 90, "kind": "access"}],
        "root_prefix": "10.0.0.0/24",
        "subnets": [{"name": "Users", "hosts": 100, "vlan": 10, "site": "Site"}],
        "sites": [{"name": "Site", "subnets": ["Users"], "role": "hq"}],
        "resilient": False,
        "single_as": True,
        "cloud": False,
        "local_asn": None,
        "peer_asn": None,
        "access_speed_gbps": 1,
        "uplink_speed_gbps": 10,
        "uplinks": 1,
        "forced_tier": None,
        "prices": None,
    }
    payload.update(overrides)
    if "subnets" in overrides and "sites" not in overrides:
        payload["sites"] = [
            {
                "name": "Site",
                "subnets": [item["name"] for item in overrides["subnets"]],
                "role": "hq",
            }
        ]
    return payload


def make_scenario(**overrides) -> Scenario:
    return Scenario.from_dict(scenario_dict(**overrides))
