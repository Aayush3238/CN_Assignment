"""Command-line interface.

The CLI is a thin adapter: it loads/validates a scenario, calls the headless
engine, renders the result, and optionally stores it in SQLite. Keeping logic
out of this file makes the engine testable without spawning processes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from netarchitect.core.engine import run_scenario
from netarchitect.core.errors import (
    AddressSpaceExhaustedError,
    NetArchitectError,
    PhysicalDistanceViolationError,
)
from netarchitect.core.models import ScenarioInput
from netarchitect.core.presets import PRESETS, get_preset, preset_names
from netarchitect.core.vlsm import VLSMRequest, allocate_vlsm
from netarchitect.report import (
    print_result,
    render_html,
    render_json,
    render_markdown,
)
from netarchitect.storage import (
    DEFAULT_DB,
    get_run,
    list_runs,
    save_run,
    write_export,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="NetArchitect: explainable network design and Cisco IOS config generator.",
)
presets_app = typer.Typer(help="Inspect the built-in scenarios.")
runs_app = typer.Typer(help="Inspect persisted run history.")
app.add_typer(presets_app, name="presets")
app.add_typer(runs_app, name="runs")

console = Console()
error_console = Console(stderr=True)

FORMATS = {"table", "json", "md", "html"}


def _fail(message: str, code: int = 2) -> None:
    """Print a clean error and exit with a meaningful status code."""
    error_console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(code=code)


def _format_validation_error(exc: ValidationError) -> str:
    """Turn pydantic's structured error list into a single readable line."""
    parts = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "input"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "report"


def _distance_label(distance_m: float) -> str:
    """Compact distance formatting for tables."""
    if distance_m >= 1000:
        return f"{distance_m / 1000:g} km"
    return f"{distance_m:g} m"


def _read_scenario(path: Path) -> ScenarioInput:
    """Parse and validate a custom JSON scenario."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        _fail(f"cannot read {path}: {exc}")
    except json.JSONDecodeError as exc:
        _fail(f"{path} is not valid JSON: {exc}")
    try:
        return ScenarioInput.model_validate(raw)
    except ValidationError as exc:
        _fail(_format_validation_error(exc))


def _resolve_scenario(preset: str | None, input_file: Path | None) -> ScenarioInput:
    """Require exactly one scenario source: preset or JSON file."""
    if bool(preset) == bool(input_file):
        _fail("provide exactly one of --preset or --input")
    if preset:
        try:
            return get_preset(preset)
        except KeyError as exc:
            _fail(str(exc))
    assert input_file is not None
    return _read_scenario(input_file)


def _run_engine(scenario: ScenarioInput):
    """Run the engine and map domain errors to CLI exit codes."""
    try:
        return run_scenario(scenario)
    except AddressSpaceExhaustedError as exc:
        _fail(str(exc), code=3)
    except PhysicalDistanceViolationError as exc:
        _fail(str(exc), code=2)
    except NetArchitectError as exc:
        _fail(str(exc), code=2)
    except ValueError as exc:
        _fail(str(exc), code=2)


# --------------------------------------------------------------------------
# presets
# --------------------------------------------------------------------------
@presets_app.command("list")
def presets_list() -> None:
    """List the three built-in scenarios."""
    table = Table(title="Presets")
    table.add_column("Name")
    table.add_column("Endpoints", justify="right")
    table.add_column("Access", justify="right")
    table.add_column("Backbone", justify="right")
    table.add_column("WAN", justify="right")
    table.add_column("Description", overflow="fold")
    for name in preset_names():
        preset = PRESETS[name]
        table.add_row(
            name,
            str(preset.endpoints),
            _distance_label(preset.access_distance_m),
            _distance_label(preset.backbone_distance_m)
            if preset.backbone_distance_m
            else "-",
            _distance_label(preset.wan_distance_m)
            if preset.wan_distance_m
            else "-",
            preset.description,
        )
    console.print(table)


@presets_app.command("show")
def presets_show(name: str = typer.Argument(..., help="Preset name or alias")) -> None:
    """Show the full validated JSON for one preset."""
    try:
        preset = get_preset(name)
    except KeyError as exc:
        _fail(str(exc))
    typer.echo(preset.model_dump_json(indent=2))


# --------------------------------------------------------------------------
# plan / validate / vlsm / export
# --------------------------------------------------------------------------
@app.command()
def plan(
    preset: str | None = typer.Option(None, "--preset", "-p", help="Preset name or alias"),
    input_file: Path | None = typer.Option(
        None, "--input", "-i", help="Custom scenario JSON file", exists=True, dir_okay=False
    ),
    fmt: str = typer.Option("table", "--format", "-f", help="table|json|md|html"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Write the rendered report to this path"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite run-history path"),
    save: bool = typer.Option(True, "--save/--no-save", help="Persist the run to SQLite"),
) -> None:
    """Run the decision engine for a preset or custom scenario."""
    fmt = fmt.lower()
    if fmt not in FORMATS:
        _fail(f"unknown format '{fmt}'. Choose from: {', '.join(sorted(FORMATS))}")
    if fmt == "table" and out is not None:
        _fail("--out requires --format json, md, or html")

    scenario = _resolve_scenario(preset, input_file)
    result = _run_engine(scenario)

    run_id = save_run(result, db) if save else None

    if fmt == "table":
        print_result(result, console)
    elif fmt == "json":
        text = render_json(result)
        if out:
            out.write_text(text, encoding="utf-8")
            console.print(f"Wrote JSON report to {out}")
        else:
            typer.echo(text)
    elif fmt == "md":
        text = render_markdown(result)
        if out:
            out.write_text(text, encoding="utf-8")
            console.print(f"Wrote Markdown report to {out}")
        else:
            typer.echo(text)
    else:  # html
        target = out or Path(f"{_slug(scenario.profile)}-report.html")
        target.write_text(render_html(result), encoding="utf-8")
        console.print(f"Wrote HTML report to {target}")

    if run_id is not None:
        # Keep stdout clean for machine-readable formats; status goes to stderr.
        message = f"Run saved as #{run_id} in {db}"
        if fmt == "table":
            console.print(message)
        else:
            error_console.print(message)


@app.command()
def validate(
    input_file: Path = typer.Argument(..., exists=True, dir_okay=False, help="Scenario JSON file"),
) -> None:
    """Validate a custom scenario and confirm the engine can run it."""
    scenario = _read_scenario(input_file)
    _run_engine(scenario)
    console.print(
        f"[green]Valid[/green] {scenario.profile}: {scenario.endpoints} endpoints, "
        f"{len(scenario.vlans)} VLANs, root {scenario.root_prefix}."
    )


@app.command()
def vlsm(
    root_prefix: str = typer.Argument(..., help="Root IPv4 prefix, e.g. 10.0.0.0/16"),
    hosts: str = typer.Option(..., "--hosts", "-H", help="Comma-separated host counts, largest first or not"),
    names: str | None = typer.Option(None, "--names", help="Comma-separated subnet names"),
    fmt: str = typer.Option("table", "--format", "-f", help="table|json|md"),
) -> None:
    """Allocate VLSM subnets without running a full scenario."""
    fmt = fmt.lower()
    if fmt not in {"table", "json", "md"}:
        _fail("--format must be table, json, or md")

    try:
        host_values = [int(value.strip()) for value in hosts.split(",") if value.strip()]
    except ValueError:
        _fail("--hosts must be a comma-separated list of integers")
    if not host_values:
        _fail("--hosts requires at least one value")

    if names:
        labels = [name.strip() for name in names.split(",") if name.strip()]
        if len(labels) != len(host_values):
            _fail("--names must contain the same number of entries as --hosts")
    else:
        labels = [f"subnet-{index}" for index in range(1, len(host_values) + 1)]

    requests = [
        VLSMRequest(name=label, hosts=count)
        for label, count in zip(labels, host_values)
    ]

    try:
        allocation = allocate_vlsm(root_prefix, requests)
    except AddressSpaceExhaustedError as exc:
        _fail(str(exc), code=3)
    except ValueError as exc:
        _fail(str(exc), code=2)

    if fmt == "json":
        typer.echo(allocation.model_dump_json(indent=2))
        return

    if fmt == "md":
        lines = [
            f"# VLSM allocation from {allocation.utilization.root_prefix}",
            "",
            "| Name | Requested | CIDR | Wildcard | Gateway | Usable |",
            "|---|---|---|---|---|---|",
        ]
        for subnet in allocation.subnets:
            lines.append(
                f"| {subnet.name} | {subnet.requested_hosts} | {subnet.cidr} | "
                f"{subnet.wildcard} | {subnet.gateway} | {subnet.usable_hosts} |"
            )
        typer.echo("\n".join(lines))
        return

    table = Table(title=f"VLSM allocation from {allocation.utilization.root_prefix}")
    table.add_column("Name")
    table.add_column("Requested", justify="right")
    table.add_column("CIDR")
    table.add_column("Wildcard")
    table.add_column("Gateway")
    table.add_column("Usable", justify="right")
    for subnet in allocation.subnets:
        table.add_row(
            subnet.name,
            str(subnet.requested_hosts),
            subnet.cidr,
            subnet.wildcard,
            subnet.gateway or "-",
            str(subnet.usable_hosts),
        )
    console.print(table)
    console.print(
        f"Address utilisation: {allocation.utilization.address_pct:.2f}% "
        f"({allocation.utilization.allocated_addresses}/"
        f"{allocation.utilization.root_addresses}); host utilisation: "
        f"{allocation.utilization.host_pct:.2f}%."
    )


@app.command()
def export(
    run_id: int = typer.Argument(..., help="Run id from 'netarchitect runs list'"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output directory (default exports/run-<id>)"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite run-history path"),
) -> None:
    """Export configs, rationale, JSON, and an HTML report for a stored run."""
    result = get_run(run_id, db)
    if result is None:
        _fail(f"run #{run_id} not found in {db}")
    target = out or Path("exports") / f"run-{run_id}"
    paths = write_export(result, target)
    console.print(f"Exported {len(paths)} file(s) to {target}")
    for path in paths:
        console.print(f"  {path.name}")


# --------------------------------------------------------------------------
# runs
# --------------------------------------------------------------------------
@runs_app.command("list")
def runs_list(db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite run-history path")) -> None:
    """List stored runs, newest first."""
    rows = list_runs(db)
    if not rows:
        console.print("No runs recorded yet. Use 'netarchitect plan ...' first.")
        return

    table = Table(title="Run history")
    table.add_column("ID", justify="right")
    table.add_column("Created (UTC)")
    table.add_column("Profile")
    table.add_column("Endpoints", justify="right")
    table.add_column("Subnets", justify="right")
    table.add_column("Host use", justify="right")
    table.add_column("Media", overflow="fold")
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["created_at"],
            row["profile"],
            str(row["endpoints"]),
            str(row["subnet_count"]),
            f"{row['host_utilization']:.2f}%",
            row["media_summary"] or "-",
        )
    console.print(table)


@runs_app.command("show")
def runs_show(
    run_id: int = typer.Argument(..., help="Run id"),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="SQLite run-history path"),
) -> None:
    """Re-render a stored run."""
    result = get_run(run_id, db)
    if result is None:
        _fail(f"run #{run_id} not found in {db}")
    print_result(result, console)


@app.command()
def version() -> None:
    """Print the CLI version."""
    from netarchitect import __version__

    console.print(f"netarchitect {__version__}")


if __name__ == "__main__":  # pragma: no cover - convenience for `python -m`
    app()
