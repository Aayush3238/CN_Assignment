from __future__ import annotations

import pytest

from netarchitect.core.errors import InvalidParameterError
from netarchitect.core.spec import Scenario, load_preset, load_scenario_file
from tests.helpers import make_scenario, scenario_dict


def test_valid_minimal_scenario():
    scenario = make_scenario()
    assert scenario.name == "test"
    assert scenario.root_prefix == "10.0.0.0/24"
    assert len(scenario.subnets) == 1


def test_boolean_is_not_accepted_as_integer():
    with pytest.raises(InvalidParameterError, match="endpoints"):
        Scenario.from_dict(scenario_dict(endpoints=True))


def test_zero_distance_rejected():
    with pytest.raises(InvalidParameterError, match="distance_m"):
        Scenario.from_dict(
            scenario_dict(links=[{"name": "bad", "distance_m": 0, "kind": "access"}])
        )


def test_non_numeric_distance_rejected():
    with pytest.raises(InvalidParameterError, match="distance_m"):
        Scenario.from_dict(
            scenario_dict(links=[{"name": "bad", "distance_m": "90", "kind": "access"}])
        )


def test_blank_name_rejected():
    with pytest.raises(InvalidParameterError, match="name"):
        Scenario.from_dict(scenario_dict(name="   "))


def test_duplicate_vlan_rejected():
    with pytest.raises(InvalidParameterError, match="already assigned"):
        Scenario.from_dict(
            scenario_dict(
                subnets=[
                    {"name": "A", "hosts": 10, "vlan": 10, "site": "Site"},
                    {"name": "B", "hosts": 10, "vlan": 10, "site": "Site"},
                ],
                sites=[{"name": "Site", "subnets": ["A", "B"]}],
            )
        )


def test_reserved_vlan_rejected():
    with pytest.raises(InvalidParameterError, match="reserved"):
        Scenario.from_dict(
            scenario_dict(subnets=[{"name": "A", "hosts": 10, "vlan": 999, "site": "Site"}])
        )


def test_subnet_claimed_by_two_sites_rejected():
    with pytest.raises(InvalidParameterError, match="claimed by both"):
        Scenario.from_dict(
            scenario_dict(
                sites=[
                    {"name": "One", "subnets": ["Users"]},
                    {"name": "Two", "subnets": ["Users"]},
                ]
            )
        )


def test_prices_must_include_all_three_roles():
    with pytest.raises(InvalidParameterError, match="core"):
        Scenario.from_dict(
            scenario_dict(prices={"access": 1000, "distribution": 2000})
        )


def test_bad_root_prefix_rejected():
    with pytest.raises(InvalidParameterError, match="root_prefix"):
        Scenario.from_dict(scenario_dict(root_prefix="10.0.0.0/33"))


def test_unknown_preset_rejected():
    with pytest.raises(InvalidParameterError, match="unknown preset"):
        load_preset("does-not-exist")


def test_presets_load_and_have_expected_names():
    assert load_preset("campus").name == "campus"
    assert load_preset("metro").name == "metro"
    assert load_preset("wan").name == "wan"
    assert load_preset("campus-lan").name == "campus"


def test_with_overrides_revalidates():
    scenario = make_scenario()
    changed = scenario.with_overrides(endpoints=5000)
    assert changed.endpoints == 5000
    with pytest.raises(InvalidParameterError):
        scenario.with_overrides(endpoints=True)


def test_load_scenario_file(tmp_path):
    path = tmp_path / "scenario.json"
    import json

    path.write_text(json.dumps(scenario_dict()), encoding="utf-8")
    assert load_scenario_file(path).name == "test"


def test_missing_file_rejected(tmp_path):
    with pytest.raises(InvalidParameterError, match="not found"):
        load_scenario_file(tmp_path / "missing.json")
