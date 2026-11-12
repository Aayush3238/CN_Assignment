from __future__ import annotations

import json

from typer.testing import CliRunner

from netarchitect.cli import app
from tests.helpers import scenario_dict

runner = CliRunner()


def test_list_presets():
    result = runner.invoke(app, ["list-presets"])
    assert result.exit_code == 0
    assert "campus" in result.output
    assert "metro" in result.output
    assert "wan" in result.output


def test_explain_campus():
    result = runner.invoke(app, ["explain", "campus"])
    assert result.exit_code == 0
    assert "Three-tier" in result.output
    assert "OSPF Area 0" in result.output


def test_explain_json():
    result = runner.invoke(app, ["explain", "metro", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["selected"]["topology"]["tier"] == "Collapsed core"


def test_run_writes_three_artifacts(tmp_path):
    result = runner.invoke(app, ["run", "--preset", "campus", "--out", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "campus.txt").exists()
    assert (tmp_path / "campus-plan.json").exists()
    assert (tmp_path / "campus-rationale.md").exists()
    assert "! ===== DEVICE: campus-core1 =====" in (tmp_path / "campus.txt").read_text(
        encoding="utf-8"
    )


def test_validate_custom_scenario(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(json.dumps(scenario_dict()), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_validate_bad_json_exits_2(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 2


def test_vlsm_exhaustion_exits_3():
    result = runner.invoke(app, ["vlsm", "10.0.0.0/24", "--hosts", "500,400"])
    assert result.exit_code == 3


def test_vlsm_success():
    result = runner.invoke(app, ["vlsm", "10.0.0.0/16", "--hosts", "500,200,100,50"])
    assert result.exit_code == 0
    assert "88.5% address use" in result.output


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "netarchitect" in result.output
