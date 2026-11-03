"""Rendering helpers: terminal tables, Markdown, JSON, and static HTML.

All renderers consume the same ``RunResult`` so the CLI and exported artifacts
cannot drift apart. The HTML output is self-contained (inline CSS) and requires
no server, which keeps the project CLI-only.
"""

from __future__ import annotations

import html

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from netarchitect.core.models import RunResult


def render_json(result: RunResult) -> str:
    """Pretty JSON for scripts and the exported run bundle."""
    return result.model_dump_json(indent=2)


def _md(value: object) -> str:
    """Escape a value for a Markdown table cell."""
    return str(value).replace("|", "\\|")


def _distance_label(distance_m: float) -> str:
    """Show metres below 1 km and kilometres above it."""
    if distance_m >= 1000:
        return f"{distance_m / 1000:g} km"
    return f"{distance_m:g} m"


def render_markdown(result: RunResult) -> str:
    """Human-readable Markdown report (used for export and documentation)."""
    scenario = result.scenario
    lines: list[str] = [
        f"# NetArchitect Report: {scenario.profile}",
        "",
        scenario.description,
        "",
        "## Scenario",
        "",
        "| Parameter | Value |",
        "|---|---|",
        f"| Endpoints | {scenario.endpoints} |",
        f"| Buildings | {scenario.buildings} |",
        f"| Remote sites | {scenario.remote_sites} |",
        f"| Root prefix | {result.utilization.root_prefix} |",
        f"| Resiliency | {scenario.resiliency} |",
        f"| Cloud VPC | {scenario.cloud_vpc} |",
        "",
        "## Layer 1 media",
        "",
        "| Link | Distance | Media | Transceiver | Standard |",
        "|---|---|---|---|---|",
    ]

    for item in result.media:
        lines.append(
            f"| {_md(item.link)} | {_distance_label(item.distance_m)} | "
            f"{_md(item.media)} | {_md(item.transceiver)} | "
            f"{_md(item.standard)} |"
        )

    lines.extend(
        [
            "",
            "## VLAN plan",
            "",
            "| VLAN | Name | Subnet | Gateway | Trunk allowed | PoE |",
            "|---|---|---|---|---|---|",
        ]
    )
    for vlan in result.vlans:
        lines.append(
            f"| {vlan.vlan_id} | {_md(vlan.name)} | {_md(vlan.subnet or '-')} | "
            f"{_md(vlan.gateway or '-')} | "
            f"{_md(','.join(str(v) for v in vlan.trunk_allowed))} | "
            f"{'yes' if vlan.poe else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## VLSM allocation",
            "",
            "| Name | Requested | CIDR | Wildcard | Gateway | Broadcast | Usable |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for subnet in result.subnets:
        lines.append(
            f"| {_md(subnet.name)} | {subnet.requested_hosts} | {subnet.cidr} | "
            f"{subnet.wildcard} | {_md(subnet.gateway)} | {subnet.broadcast} | "
            f"{subnet.usable_hosts} |"
        )

    utilization = result.utilization
    lines.extend(
        [
            "",
            f"Address-space utilisation: **{utilization.address_pct:.2f}%** "
            f"({utilization.allocated_addresses}/{utilization.root_addresses}); "
            f"host utilisation: **{utilization.host_pct:.2f}%** "
            f"({utilization.requested_hosts}/{utilization.usable_hosts}).",
            "",
            "## Routing",
            "",
            f"**{result.routing.protocol}** ({result.routing.rule_id})",
            "",
            result.routing.rationale,
            "",
            "| Area | Subnets |",
            "|---|---|",
        ]
    )
    for area, cidrs in result.routing.areas.items():
        lines.append(f"| {area} | {_md(', '.join(cidrs))} |")

    if result.routing.summarization:
        lines.extend(["", "Summarisation commands:", ""])
        for command in result.routing.summarization:
            lines.append(f"- `{command}`")

    lines.extend(["", "## Explainability log", ""])
    for entry in result.rationales:
        lines.extend(
            [
                f"### {entry.rule_id}: {entry.choice}",
                "",
                f"*Domain:* {entry.domain}  ",
                f"*Condition:* {entry.condition}  ",
                f"*Standard:* {entry.standard or 'n/a'}",
                "",
                f"> {entry.rationale}",
                "",
            ]
        )

    lines.extend(["## Generated configurations", ""])
    for filename in result.configs:
        lines.append(f"- `{filename}`")
    lines.append("")
    return "\n".join(lines)


def print_result(result: RunResult, console: Console | None = None) -> None:
    """Print a compact but complete terminal report."""
    console = console or Console()
    scenario = result.scenario

    console.print(
        Panel.fit(
            f"[bold]{scenario.profile}[/bold]\n{scenario.description}",
            title="NetArchitect",
        )
    )

    media_table = Table(title="L1 media selection")
    media_table.add_column("Link")
    media_table.add_column("Distance", justify="right")
    media_table.add_column("Media")
    media_table.add_column("Transceiver")
    for item in result.media:
        distance = _distance_label(item.distance_m)
        media_table.add_row(item.link, distance, item.media, item.transceiver)
    console.print(media_table)

    vlan_table = Table(title="VLAN plan")
    vlan_table.add_column("ID", justify="right")
    vlan_table.add_column("Name")
    vlan_table.add_column("Subnet")
    vlan_table.add_column("Gateway")
    vlan_table.add_column("Trunk allowed")
    vlan_table.add_column("PoE")
    for vlan in result.vlans:
        vlan_table.add_row(
            str(vlan.vlan_id),
            vlan.name,
            vlan.subnet or "-",
            vlan.gateway or "-",
            ",".join(str(v) for v in vlan.trunk_allowed),
            "yes" if vlan.poe else "no",
        )
    console.print(vlan_table)

    subnet_table = Table(title="VLSM allocation")
    subnet_table.add_column("Name")
    subnet_table.add_column("Requested", justify="right")
    subnet_table.add_column("CIDR")
    subnet_table.add_column("Wildcard")
    subnet_table.add_column("Gateway")
    subnet_table.add_column("Usable", justify="right")
    for subnet in result.subnets:
        subnet_table.add_row(
            subnet.name,
            str(subnet.requested_hosts),
            subnet.cidr,
            subnet.wildcard,
            subnet.gateway or "-",
            str(subnet.usable_hosts),
        )
    console.print(subnet_table)

    utilization = result.utilization
    console.print(
        f"Utilisation: [bold]{utilization.address_pct:.2f}%[/bold] of "
        f"{utilization.root_prefix} allocated; "
        f"host utilisation {utilization.host_pct:.2f}%."
    )
    console.print(f"Routing: [bold]{result.routing.protocol}[/bold]")
    console.print(f"  {result.routing.rationale}")

    rationale_table = Table(title="Explainability log")
    rationale_table.add_column("Rule")
    rationale_table.add_column("Domain")
    rationale_table.add_column("Choice")
    rationale_table.add_column("Rationale", overflow="fold")
    for entry in result.rationales:
        rationale_table.add_row(
            entry.rule_id, entry.domain, entry.choice, entry.rationale
        )
    console.print(rationale_table)
    console.print("Configurations: " + ", ".join(result.configs))


def render_html(result: RunResult) -> str:
    """Render a self-contained HTML report (no server, no external assets)."""
    scenario = result.scenario

    media_rows = "".join(
        f"<tr><td>{html.escape(item.link)}</td>"
        f"<td>{_distance_label(item.distance_m)}</td>"
        f"<td>{html.escape(item.media)}</td>"
        f"<td>{html.escape(item.transceiver)}</td>"
        f"<td>{html.escape(item.standard)}</td></tr>"
        for item in result.media
    )

    vlan_rows = "".join(
        f"<tr><td>{vlan.vlan_id}</td><td>{html.escape(vlan.name)}</td>"
        f"<td>{html.escape(vlan.subnet or '-')}</td>"
        f"<td>{html.escape(vlan.gateway or '-')}</td>"
        f"<td>{html.escape(','.join(str(v) for v in vlan.trunk_allowed))}</td>"
        f"<td>{'yes' if vlan.poe else 'no'}</td></tr>"
        for vlan in result.vlans
    )

    subnet_rows = "".join(
        f"<tr><td>{html.escape(subnet.name)}</td><td>{subnet.requested_hosts}</td>"
        f"<td>{subnet.cidr}</td><td>{subnet.wildcard}</td>"
        f"<td>{html.escape(subnet.gateway or '-')}</td>"
        f"<td>{subnet.broadcast}</td><td>{subnet.usable_hosts}</td></tr>"
        for subnet in result.subnets
    )

    rationale_cards = "".join(
        f"<article class='card'><h3>{html.escape(entry.rule_id)}: "
        f"{html.escape(entry.choice)}</h3>"
        f"<p class='meta'>{html.escape(entry.domain)} &middot; "
        f"{html.escape(entry.condition)} &middot; "
        f"{html.escape(entry.standard or 'n/a')}</p>"
        f"<p>{html.escape(entry.rationale)}</p></article>"
        for entry in result.rationales
    )

    config_blocks = "".join(
        f"<details><summary>{html.escape(filename)}</summary>"
        f"<pre>{html.escape(content)}</pre></details>"
        for filename, content in result.configs.items()
    )

    area_rows = "".join(
        f"<tr><td>{html.escape(area)}</td>"
        f"<td>{html.escape(', '.join(cidrs))}</td></tr>"
        for area, cidrs in result.routing.areas.items()
    )

    utilization = result.utilization
    summary_commands = "".join(
        f"<li><code>{html.escape(command)}</code></li>"
        for command in result.routing.summarization
    ) or "<li>No summarisation opportunity detected.</li>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NetArchitect - {html.escape(scenario.profile)}</title>
<style>
  :root {{ color-scheme: light dark; --accent: #0b6e4f; --muted: #667; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif;
         margin: 0 auto; max-width: 1100px; padding: 2rem; line-height: 1.5; }}
  h1 {{ margin-bottom: .25rem; }}
  .lede {{ color: var(--muted); margin-top: 0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
  th, td {{ border: 1px solid #8884; padding: .45rem .6rem; text-align: left; }}
  th {{ background: #8881; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }}
  .card {{ border: 1px solid #8884; border-radius: .6rem; padding: 1rem; }}
  .card h3 {{ margin: 0 0 .35rem; font-size: 1rem; }}
  .meta {{ color: var(--muted); font-size: .85rem; margin-top: 0; }}
  details {{ border: 1px solid #8884; border-radius: .5rem; margin: .6rem 0; padding: .6rem .8rem; }}
  summary {{ cursor: pointer; font-weight: 600; }}
  pre {{ overflow-x: auto; padding: .8rem; background: #8881; border-radius: .4rem; }}
  .stats {{ display: flex; gap: 2rem; flex-wrap: wrap; }}
  .stats strong {{ font-size: 1.4rem; color: var(--accent); }}
</style>
</head>
<body>
<h1>{html.escape(scenario.profile)}</h1>
<p class="lede">{html.escape(scenario.description)}</p>

<div class="stats">
  <div><strong>{utilization.address_pct:.2f}%</strong><br>address utilisation</div>
  <div><strong>{utilization.host_pct:.2f}%</strong><br>host utilisation</div>
  <div><strong>{len(result.subnets)}</strong><br>subnets</div>
  <div><strong>{len(result.vlans)}</strong><br>VLANs</div>
</div>

<h2>Layer 1 media</h2>
<table><thead><tr><th>Link</th><th>Distance</th><th>Media</th><th>Transceiver</th><th>Standard</th></tr></thead>
<tbody>{media_rows}</tbody></table>

<h2>VLAN plan</h2>
<table><thead><tr><th>VLAN</th><th>Name</th><th>Subnet</th><th>Gateway</th><th>Trunk allowed</th><th>PoE</th></tr></thead>
<tbody>{vlan_rows}</tbody></table>

<h2>VLSM allocation</h2>
<table><thead><tr><th>Name</th><th>Requested</th><th>CIDR</th><th>Wildcard</th><th>Gateway</th><th>Broadcast</th><th>Usable</th></tr></thead>
<tbody>{subnet_rows}</tbody></table>

<h2>Routing</h2>
<p><strong>{html.escape(result.routing.protocol)}</strong> ({html.escape(result.routing.rule_id)})</p>
<p>{html.escape(result.routing.rationale)}</p>
<table><thead><tr><th>Area</th><th>Subnets</th></tr></thead><tbody>{area_rows}</tbody></table>
<ul>{summary_commands}</ul>

<h2>Explainability log</h2>
<div class="grid">{rationale_cards}</div>

<h2>Generated configurations</h2>
{config_blocks}
</body>
</html>
"""
