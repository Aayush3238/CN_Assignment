"""Terminal, JSON, and Markdown renderers.

The dashboard has its own Jinja2 template; this module is for the CLI and for
the files written by ``netarchitect run``.  Every renderer reads the same
``Analysis`` object, so the numbers cannot drift between output formats.
"""

from __future__ import annotations

import json
from typing import Any

from netarchitect.core.design import Analysis
from netarchitect.core.media import format_distance


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def render_json(analysis: Analysis, *, include_configs: bool = True) -> str:
    return json.dumps(
        analysis.to_dict(include_configs=include_configs),
        indent=2,
        ensure_ascii=False,
    )


def render_markdown(analysis: Analysis) -> str:
    scenario = analysis.scenario
    plan = analysis.selected
    alt = analysis.alternate
    lines: list[str] = [
        f"# NetArchitect design: {scenario.name}",
        "",
        f"> {scenario.description}",
        "",
        "## Scenario",
        "",
    ]
    lines += _table(
        ["Field", "Value"],
        [
            ["Endpoints", scenario.endpoints],
            ["Buildings", scenario.buildings],
            ["Root prefix", scenario.root_prefix],
            ["Resilient", "yes" if scenario.resilient else "no"],
            ["Single autonomous system", "yes" if scenario.single_as else "no"],
            ["Cloud boundary", "yes" if scenario.cloud else "no"],
            ["Access speed", f"{scenario.access_speed_gbps} Gb/s"],
            ["Uplinks", f"{scenario.uplinks} x {scenario.uplink_speed_gbps} Gb/s"],
        ],
    )
    lines += ["", "## Selected design", ""]
    lines += _table(
        ["Item", "Selected"],
        [
            ["Topology", f"{plan.topology.tier} ({plan.topology.switch_count} switches)"],
            ["Routing", plan.routing.protocol],
            ["Spanning tree", plan.switching.stp],
            ["First-hop redundancy", plan.switching.fhrp],
            ["Address utilisation", f"{plan.vlsm.utilization:.1f}%"],
            ["Oversubscription", plan.topology.ratio],
        ],
    )

    lines += ["", "## Media selection", ""]
    media_rows: list[list[Any]] = []
    for item in plan.media:
        budget = (
            f"{item.loss_db:.2f} / {item.budget_db:.1f} dB"
            if item.loss_db is not None and item.budget_db is not None
            else "-"
        )
        media_rows.append(
            [
                item.link,
                item.distance_label,
                item.medium,
                item.transceiver,
                budget,
                item.severity,
            ]
        )
    lines += _table(
        ["Link", "Distance", "Medium", "Transceiver", "Loss / budget", "Severity"],
        media_rows,
    )

    lines += ["", "## Decision log", ""]
    for decision in plan.decisions:
        lines += [
            f"### {decision.category}: {decision.choice}",
            "",
            f"**Why.** {decision.reason}",
            "",
            f"**Standard.** {decision.standard}",
            "",
            f"**Severity.** {decision.severity}",
            "",
        ]

    lines += ["## Address plan", ""]
    address_rows = [
        [
            block.name,
            block.vlan if block.vlan is not None else "-",
            block.cidr,
            block.mask,
            block.wildcard,
            block.gateway,
            block.usable,
            f"{block.utilization:.0f}%",
        ]
        for block in plan.vlsm.blocks
    ]
    lines += _table(
        ["Subnet", "VLAN", "CIDR", "Mask", "Wildcard", "Gateway", "Usable", "Use"],
        address_rows,
    )

    lines += ["", "## Alternate design", ""]
    lines += _table(
        ["Item", "Selected", "Alternate"],
        [
            ["Topology", plan.topology.tier, alt.topology.tier],
            ["Routing", plan.routing.protocol, alt.routing.protocol],
            ["Switches", plan.topology.switch_count, alt.topology.switch_count],
            ["Violations", len(plan.violations), len(alt.violations)],
        ],
    )
    if alt.violations:
        lines += ["", "Alternate violations:", ""]
        lines += [f"- {violation}" for violation in alt.violations]

    lines += ["", "## Generated configurations", ""]
    lines += [f"- `{hostname}`" for hostname in sorted(analysis.device_configs)]
    lines += [
        "",
        "The combined Packet Tracer file is "
        f"`exports/{analysis.export_filename}`; each device starts at a "
        "`! ===== DEVICE:` banner.",
        "",
        "## Credentials",
        "",
        "Lab only: enable secret and local user `admin` use `NetArchitect-Lab-123`; "
        "the IPsec pre-shared key is `NetArchitect-Lab-Key`. Replace both before "
        "any real deployment.",
        "",
    ]
    return "\n".join(lines)


def render_console(console, analysis: Analysis) -> None:
    """Print the summary, media, decisions, and address plan with Rich."""
    from rich.panel import Panel
    from rich.table import Table

    scenario = analysis.scenario
    plan = analysis.selected
    console.print(
        Panel(
            f"[bold]{scenario.name}[/bold]\n{scenario.description}",
            title="NetArchitect",
            expand=False,
        )
    )

    summary = Table(title="Design summary", show_lines=False)
    summary.add_column("Item", style="cyan", no_wrap=True)
    summary.add_column("Selected", style="white")
    summary.add_row("Topology", f"{plan.topology.tier} ({plan.topology.switch_count} switches)")
    summary.add_row("Routing", plan.routing.protocol)
    summary.add_row("Spanning tree", plan.switching.stp)
    summary.add_row("First-hop redundancy", plan.switching.fhrp)
    summary.add_row("Address utilisation", f"{plan.vlsm.utilization:.1f}%")
    summary.add_row("Oversubscription", plan.topology.ratio)
    console.print(summary)

    media = Table(title="Layer-1 media")
    media.add_column("Link")
    media.add_column("Distance", justify="right")
    media.add_column("Medium")
    media.add_column("Transceiver")
    media.add_column("Loss / budget", justify="right")
    media.add_column("Severity")
    for item in plan.media:
        budget = (
            f"{item.loss_db:.2f} / {item.budget_db:.1f} dB"
            if item.loss_db is not None and item.budget_db is not None
            else "-"
        )
        media.add_row(
            item.link,
            item.distance_label,
            item.medium,
            item.transceiver,
            budget,
            item.severity,
        )
    console.print(media)

    address = Table(title=f"VLSM plan ({plan.vlsm.root})")
    address.add_column("Subnet")
    address.add_column("VLAN", justify="right")
    address.add_column("CIDR")
    address.add_column("Mask")
    address.add_column("Wildcard")
    address.add_column("Gateway")
    address.add_column("Usable", justify="right")
    address.add_column("Use", justify="right")
    for block in plan.vlsm.blocks:
        address.add_row(
            block.name,
            str(block.vlan) if block.vlan is not None else "-",
            block.cidr,
            block.mask,
            block.wildcard,
            block.gateway,
            str(block.usable),
            f"{block.utilization:.0f}%",
        )
    console.print(address)

    decisions = Table(title="Decision log", show_lines=True)
    decisions.add_column("Category", style="cyan", no_wrap=True)
    decisions.add_column("Choice", style="white")
    decisions.add_column("Severity", justify="center")
    decisions.add_column("Why", overflow="fold")
    for decision in plan.decisions:
        style = {
            "violation": "red",
            "warning": "yellow",
            "info": "green",
        }.get(decision.severity, "white")
        decisions.add_row(
            decision.category,
            decision.choice,
            f"[{style}]{decision.severity}[/{style}]",
            decision.reason,
        )
    console.print(decisions)

    if plan.violations:
        console.print("[bold red]Selected-plan violations:[/bold red]")
        for violation in plan.violations:
            console.print(f"  - {violation}")
    if analysis.alternate.violations:
        console.print("[bold yellow]Alternate-plan violations:[/bold yellow]")
        for violation in analysis.alternate.violations:
            console.print(f"  - {violation}")
