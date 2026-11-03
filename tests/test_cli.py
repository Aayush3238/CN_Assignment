"""CLI integration tests using Typer's CliRunner."""

import json

from typer.testing import CliRunner

from netarchitect.cli import app

runner = CliRunner()


def _valid_scenario() -> dict:
    return {
        "profile": "branch-office",
        "description": "Small branch",
        "endpoints": 100,
        "access_distance_m": 80,
        "backbone_distance_m": 250,
        "root_prefix": "10.50.0.0/24",
        "vlans": [
            {"name": "Staff", "hosts": 60, "vlan_id": 10},
            {"name": "Guest", "hosts": 30, "vlan_id": 20},
            {"name": "Management", "hosts": 10, "vlan_id": 30},
        ],
    }


def test_presets_list():
    result = runner.invoke(app, ["presets", "list"])
    assert result.exit_code == 0
    assert "campus-lan" in result.output
    assert "metro-man" in result.output
    assert "global-wan" in result.output


def test_presets_show_is_json():
    result = runner.invoke(app, ["presets", "show", "campus"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["profile"] == "campus-lan"


def test_plan_json_stdout_is_clean():
    result = runner.invoke(
        app, ["plan", "--preset", "campus-lan", "--format", "json", "--no-save"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["scenario"]["profile"] == "campus-lan"
    assert payload["configs"]["switches.cfg"]
    assert payload["rationales"]


def test_plan_saves_lists_shows_and_exports(tmp_path):
    db = tmp_path / "runs.db"
    out_dir = tmp_path / "export"

    plan_result = runner.invoke(
        app, ["plan", "--preset", "campus-lan", "--db", str(db)]
    )
    assert plan_result.exit_code == 0
    assert "Run saved as #1" in plan_result.output
    assert db.exists()

    list_result = runner.invoke(app, ["runs", "list", "--db", str(db)])
    assert list_result.exit_code == 0
    assert "campus-lan" in list_result.output

    show_result = runner.invoke(app, ["runs", "show", "1", "--db", str(db)])
    assert show_result.exit_code == 0
    assert "VLSM allocation" in show_result.output

    export_result = runner.invoke(
        app,
        ["export", "1", "--out", str(out_dir), "--db", str(db)],
    )
    assert export_result.exit_code == 0
    assert (out_dir / "switches.cfg").exists()
    assert (out_dir / "router.cfg").exists()
    assert (out_dir / "rationale.md").exists()
    assert (out_dir / "run.json").exists()
    assert (out_dir / "report.html").exists()


def test_plan_html_writes_file(tmp_path):
    target = tmp_path / "report.html"
    result = runner.invoke(
        app,
        ["plan", "--preset", "metro-man", "--format", "html", "--out", str(target), "--no-save"],
    )
    assert result.exit_code == 0
    assert target.exists()
    assert "NetArchitect" in target.read_text(encoding="utf-8")


def test_validate_accepts_good_scenario(tmp_path):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(_valid_scenario()), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 0
    assert "Valid" in result.output


def test_invalid_scenario_exits_2(tmp_path):
    payload = _valid_scenario()
    payload["endpoints"] = 10  # less than the VLAN host total
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = runner.invoke(app, ["validate", str(path)])
    assert result.exit_code == 2
    assert "exceed declared endpoints" in result.output


def test_vlsm_command():
    result = runner.invoke(app, ["vlsm", "10.0.0.0/24", "--hosts", "100,50,20"])
    assert result.exit_code == 0
    assert "10.0.0.0/25" in result.output
    assert "10.0.0.128/26" in result.output


def test_vlsm_exhaustion_exits_3():
    result = runner.invoke(app, ["vlsm", "10.0.0.0/24", "--hosts", "200,200"])
    assert result.exit_code == 3
    assert "exhausted" in result.output


def test_plan_requires_exactly_one_source():
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 2
    assert "exactly one" in result.output


def test_unknown_preset_exits_2():
    result = runner.invoke(app, ["plan", "--preset", "does-not-exist"])
    assert result.exit_code == 2
    assert "unknown preset" in result.output
