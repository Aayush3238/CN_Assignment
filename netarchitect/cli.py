"""Command-line interface.

The CLI is a thin adapter: it loads and validates a scenario, calls
:func:`netarchitect.core.design.analyze`, renders the result, and optionally
writes the export bundle.  No planning rule lives in this file.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from netarchitect.core.design import analyze, design
from netarchitect.core.errors import (
    AddressSpaceExhaustedError,
    NetArchitectError,
    PhysicalDistanceViolationError,
)
from netarchitect.core.media import format_distance
from netarchitect.core.spec import (
    PRESET_NAMES,
    SubnetRequest,
    all_presets,
    load_preset,
    load_scenario_file,
)
from netarchitect.core.vlsm import allocate_vlsm
from netarchitect.report import render_console, render_json, render_markdown

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="NetArchitect: explainable network design and Cisco IOS config generator.",
)
console = Console()

EXIT_BAD_INPUT = 2
EXIT_EXHAUSTED = 3


def _fail(message: str, code: int = EXIT_BAD_INPUT) -> None:
    console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(code=code)


def _load_preset_or_fail(name: str):
    try:
        return load_preset(name)
    except NetArchitectError as exc:
        _fail(str(exc))


def _load_scenario_or_fail(preset: str | None, input_path: Path | None):
    try:
        if input_path is not None:
            return load_scenario_file(input_path)
        if preset:
            return load_preset(preset)
    except NetArchitectError as exc:
        _fail(str(exc))
    _fail("provide --preset <campus|metro|wan> or --input <scenario.json>")


@app.command("list-presets")
def list_presets() -> None:
    """List the three built-in scenarios."""
    table = Table(title="NetArchitect presets")
    table.add_column("Preset", style="cyan", no_wrap=True)
    table.add_column("Endpoints", justify="right")
    table.add_column("Buildings", justify="right")
    table.add_column("Longest link", justify="right")
    table.add_column("Root")
    table.add_column("Focus", overflow="fold")
    try:
        scenarios = all_presets()
    except NetArchitectError as exc:
        _fail(str(exc))
    for name in PRESET_NAMES:
        scenario = scenarios[name]
        longest = max(link.distance_m for link in scenario.links)
        focus = scenario.description
        table.add_row(
            name,
            str(scenario.endpoints),
            str(scenario.buildings),
            format_distance(longest),
            scenario.root_prefix,
            focus,
        )
    console.print(table)


@app.command()
def explain(
    preset: str | None = typer.Argument(None, help="campus, metro, or wan"),
    input_path: Path | None = typer.Option(
        None, "--input", "-i", help="Custom scenario JSON instead of a preset"
    ),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="table, json, or md"
    ),
) -> None:
    """Explain every media, VLSM, topology, routing, and switching choice."""
    scenario = _load_scenario_or_fail(preset, input_path)
    try:
        analysis = analyze(scenario)
    except PhysicalDistanceViolationError as exc:
        _fail(str(exc))
    except AddressSpaceExhaustedError as exc:
        _fail(str(exc), EXIT_EXHAUSTED)
    except NetArchitectError as exc:
        _fail(str(exc))

    if output_format == "json":
        console.print_json(render_json(analysis, include_configs=False))
    elif output_format in {"md", "markdown"}:
        console.print(render_markdown(analysis))
    else:
        render_console(console, analysis)


@app.command()
def run(
    preset: str | None = typer.Option(None, "--preset", "-p", help="campus, metro, or wan"),
    input_path: Path | None = typer.Option(
        None, "--input", "-i", help="Custom scenario JSON instead of a preset"
    ),
    out: Path = typer.Option(Path("exports"), "--out", "-o", help="Output directory"),
) -> None:
    """Run a preset or custom scenario and write its IOS export, JSON plan, and rationale."""
    scenario = _load_scenario_or_fail(preset, input_path)
    try:
        analysis = analyze(scenario)
    except PhysicalDistanceViolationError as exc:
        _fail(str(exc))
    except AddressSpaceExhaustedError as exc:
        _fail(str(exc), EXIT_EXHAUSTED)
    except NetArchitectError as exc:
        _fail(str(exc))

    out.mkdir(parents=True, exist_ok=True)
    ios_path = out / analysis.export_filename
    json_path = out / f"{scenario.name}-plan.json"
    rationale_path = out / f"{scenario.name}-rationale.md"

    ios_path.write_text(analysis.export_text, encoding="utf-8")
    json_path.write_text(render_json(analysis), encoding="utf-8")
    rationale_path.write_text(render_markdown(analysis), encoding="utf-8")

    render_console(console, analysis)
    console.print(
        f"[bold green]Wrote[/bold green] {ios_path}, {json_path}, and {rationale_path}"
    )


@app.command()
def validate(
    path: Path = typer.Argument(..., help="Path to a custom scenario JSON file"),
) -> None:
    """Validate a custom scenario and confirm the engine can run it."""
    try:
        scenario = load_scenario_file(path)
        plan = design(scenario)
    except PhysicalDistanceViolationError as exc:
        _fail(str(exc))
    except AddressSpaceExhaustedError as exc:
        _fail(str(exc), EXIT_EXHAUSTED)
    except NetArchitectError as exc:
        _fail(str(exc))
    console.print(
        f"[bold green]OK[/bold green] {path}: {scenario.name} -> "
        f"{plan.topology.tier}, {plan.routing.protocol}, "
        f"{len(plan.vlsm.blocks)} subnets, {plan.vlsm.utilization:.1f}% address use"
    )


@app.command()
def vlsm(
    root: str = typer.Argument(..., help="Root prefix, e.g. 10.0.0.0/16"),
    hosts: str = typer.Option(..., "--hosts", "-h", help="Comma-separated host counts"),
    mode: str = typer.Option("lan", "--mode", help="lan, p2p30, or p2p31"),
) -> None:
    """Allocate VLSM subnets without running a full scenario."""
    try:
        counts = [int(item.strip()) for item in hosts.split(",") if item.strip()]
        if not counts:
            raise ValueError("at least one host count is required")
        requests = [
            SubnetRequest(name=f"Subnet{index}", hosts=count, mode=mode)
            for index, count in enumerate(counts, start=1)
        ]
        plan = allocate_vlsm(root, requests)
    except AddressSpaceExhaustedError as exc:
        _fail(str(exc), EXIT_EXHAUSTED)
    except (ValueError, NetArchitectError) as exc:
        _fail(str(exc))

    table = Table(title=f"VLSM allocation inside {plan.root}")
    table.add_column("Subnet")
    table.add_column("Hosts", justify="right")
    table.add_column("CIDR")
    table.add_column("Mask")
    table.add_column("Wildcard")
    table.add_column("Broadcast")
    table.add_column("Gateway")
    table.add_column("Usable", justify="right")
    for block in plan.blocks:
        table.add_row(
            block.name,
            str(block.hosts),
            block.cidr,
            block.mask,
            block.wildcard,
            block.broadcast or "-",
            block.gateway,
            str(block.usable),
        )
    console.print(table)
    console.print(
        f"Allocated {plan.allocated_addresses} addresses for "
        f"{plan.requested_total} requested hosts ({plan.utilization:.1f}% address use)."
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8000, help="TCP port"),
    reload: bool = typer.Option(False, "--reload", help="Reload on source changes"),
) -> None:
    """Start the web dashboard (equivalent to uvicorn netarchitect.api:app)."""
    import uvicorn

    uvicorn.run("netarchitect.api:app", host=host, port=port, reload=reload)


@app.command()
def version() -> None:
    """Print the CLI version."""
    from netarchitect import __version__

    console.print(f"netarchitect {__version__}")


if __name__ == "__main__":  # pragma: no cover
    app()
