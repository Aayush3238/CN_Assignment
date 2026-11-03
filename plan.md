# NetArchitect — Implementation Plan (CLI-only)

Source: `NetArchitect Assignment Specification-2.pdf` (CIC-307, 100 pts, due 10 Nov 2026).

Goal: a command-line utility that ingests preset/custom enterprise network parameters, runs an
algorithmic rule engine, and outputs structured recommendations plus deployment-ready Cisco IOS
configs — with a natural-language justification for every choice.

Scope decision: CLI only. The spec explicitly permits "CLI, web dashboard, or API", and the
rubric awards no points for a web UI. All effort goes into engine correctness, explainability,
subnet math, configs, and tests.

---

## 1. Scope & Deliverables

| Deliverable | Notes |
|---|---|
| Source code repo | CLI + explainability engine + unit test suite |
| `ai_audit_log.md` | Two real AI misconfigurations: prompt, buggy output, diagnosis, fix |
| 3 verification exports | Config files from the 3 preset profiles, loadable in Packet Tracer / GNS3 |
| Test suite | `pytest` covering boundaries, VLSM, wildcard masks, exhaustion |

Rubric targets: Parameter Engine 15, Explainable Engine 25, Subnet + Configs 25,
Unit Testing 15, AI Audit 20.

---

## 2. Stack

- Python 3.14 (installed); pin 3.12 in `pyproject.toml` if any dependency wheels fail.
- `typer` — CLI commands
- `pydantic` — input models and validation
- `rich` — tables, panels, rationale output
- `sqlite3` (stdlib) — optional local run history
- `pytest` — engine and CLI tests (via `typer.testing.CliRunner`)
- No web framework, no server, no frontend build step.

---

## 3. Architecture

```
netarchitect/
  core/
    models.py        # Scenario, MediaRecommendation, Subnet, RunRecord
    presets.py       # Campus LAN, Metro MAN, Global WAN
    physics.py       # distance/media rules, optical budget, boundary errors
    vlsm.py          # bitwise allocator, overlap checks, utilization
    routing.py       # OSPF single/multi-area, eBGP, summarization
    vlan.py          # 802.1Q, RSTP, PoE
    explain.py       # rule-id -> natural-language justification log
    configs/ios.py   # interfaces, trunks, SVIs, OSPF, ACLs, QoS, IPsec
    storage.py       # run history (SQLite) + exports
    report.py        # table / JSON / Markdown / static HTML rendering
  cli.py             # Typer entrypoint
tests/
```

Key principle: the engine is headless and returns plain data objects. The CLI is a thin
adapter. `report.py` renders the same run data as table, JSON, Markdown, or a self-contained
static HTML file, so no server is needed to produce a viewable report.

### Run storage (optional)

```sql
CREATE TABLE runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  profile TEXT NOT NULL,          -- preset name or "custom"
  input_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  media_summary TEXT,
  subnet_count INTEGER,
  utilization REAL
);

CREATE TABLE artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER REFERENCES runs(id),
  filename TEXT NOT NULL,
  content TEXT NOT NULL
);
```

If history is skipped, each run writes to `runs/<timestamp>-<profile>/` instead.

---

## 4. Input Model (presets + custom JSON)

Common fields: profile, scale (buildings/sites/cities), max link distance, endpoint count,
density, uplink bandwidth, resiliency requirement, PoE needs, VLAN requirements,
routing domain, cloud/colo presence.

Preset values from the spec:

| Profile | Scale | Nodes | Focus |
|---|---|---|---|
| Campus LAN | 3 buildings, <400 m | 1,600 endpoints, PoE APs | Cat6a vs MMF, 802.1Q VLANs, RSTP, single-area OSPF |
| Metro MAN | HQ + 2 remote, 15–35 km | 450 users, FinTech colo | OS2 SMF, EVPL, sub-5 ms QoS, dual-homed failover |
| Global WAN | 4 cities + cloud VPC | 2,000 IoT/scanners | IPsec VPN, multi-area OSPF/BGP, route summarization |

Validation: distances, densities, host counts, prefix sizes, resiliency flags; reject
invalid types/ranges with actionable messages.

---

## 5. Decision Engine

### 5.1 Physical media (L1)

| Condition | Recommendation | Rationale |
|---|---|---|
| Run <= 100 m (access) | Cat6a / 10GBASE-T | 802.3an 100 m limit |
| 101–400 m (backbone) | OM4 MMF / 10GBASE-SR | 850 nm dispersion/attenuation budget |
| > 400 m (MAN/WAN) | OS2 SMF / 10GBASE-LR/ER | optical budget for long reach |
| Copper requested > 100 m | raise `PhysicalDistanceViolationError` | signal attenuation warning |

Also compute a fiber optical budget (TX power - RX sensitivity - connector/splice losses)
and reject runs that exceed it.

### 5.2 VLSM allocator

- Input: root prefix (e.g. `/16`) + host-request array.
- Sort requests descending by required hosts.
- Allocate bitwise, non-overlapping subnets (network, mask, first/last host,
  broadcast, gateway).
- Use `ipaddress` for correctness; add an independent bitwise overlap check in tests.
- Output utilization efficiency = allocated host capacity / total requested capacity
  (and/or address-space used / available).
- Handle `/31` (point-to-point, RFC 3021), `/32` (loopback), and space exhaustion
  with a dedicated error.

### 5.3 L3 routing

| Condition | Selection | Rationale |
|---|---|---|
| Single AS, < 50 subnets | OSPF Area 0 | link-state fast convergence |
| Multi-site / multi-cloud | Multi-area OSPF or eBGP | routing-domain isolation, summarization |

Generate area assignments and summarization candidates; justify with RFC/standards
references where applicable.

### 5.4 L2

802.1Q VLAN plan (IDs, names, allowed trunks, native VLAN hardening), RSTP roles,
PoE budget for APs; refuse unconstrained "allow all" trunk configs.

### 5.5 Explainability

Every decision emits a record:

```json
{
  "rule_id": "L1-DIST-03",
  "inputs": {"distance_m": 22000},
  "condition": "distance_m > 400",
  "choice": "OS2 SMF / 10GBASE-LR",
  "rationale": "Selected OS2 Single-Mode Fiber because link distance (22 km) exceeds the 400 m attenuation limit of OM4 Multimode Fiber.",
  "standard": "IEEE 802.3ae"
}
```

The rationale log is serialized to JSON, shown in the CLI, and included in exported bundles.

### 5.6 IOS config generator

Copy-paste ready Cisco IOS for:
- switch access ports + PoE, trunk ports (explicit allowed VLAN list), portfast/BPDU guard
- SVIs with gateway IPs, `ip routing`
- router interfaces and OSPF (`network`, areas, passive interfaces, summarization)
- ACLs derived from VLAN policy, QoS for the Metro MAN profile, IPsec/VPN stubs for Global WAN

---

## 6. CLI

```
netarchitect presets list
netarchitect presets show campus-lan
netarchitect plan --preset campus-lan
netarchitect plan --input custom.json --format table|json|md|html
netarchitect validate custom.json
netarchitect vlsm 10.0.0.0/16 --hosts 500,200,100,50
netarchitect export <run-id> --out exports/
netarchitect runs list
netarchitect runs show <run-id>
```

`plan` executes the engine, persists a run, prints media/VLAN/routing/subnet tables and
the rationale log. `--format html` writes a self-contained static report (inline CSS) that
can be opened in any browser — a viewable artifact without running a server.

Exit codes: `0` success, `2` validation/boundary error, `3` address-space exhaustion,
`4` internal failure — useful for scripts and CI.

---

## 7. Static Report (optional, no server)

`netarchitect plan ... --format html --out report.html` renders:
- scenario summary and input parameters
- media selection + rationale log
- VLAN and routing plan
- VLSM allocation table with utilization
- collapsible IOS configs

This gives a presentable artifact for demos and the report writeup while remaining CLI-only.

---

## 8. Testing Plan

`pytest` coverage:
- Media boundaries: 99/100/101/400/401 m, copper > 100 m exception.
- Optical budget pass/fail.
- VLSM: sorted allocation, zero overlap (independent bitwise check), exhaustion,
  /31 and /32, utilization math.
- Wildcard mask calculation for multiple prefix lengths.
- Routing threshold at 50 subnets and multi-site selection.
- Preset snapshot tests (stable output structure and rationales).
- CLI tests via `typer.testing.CliRunner`: plan, validate, vlsm, export, exit codes.

---

## 9. AI Audit Log

Document two concrete AI-generated defects, e.g.:
1. Bitwise mask error causing overlapping VLSM blocks.
2. Unconstrained trunk (`switchport trunk allowed vlan all`) with no native-VLAN hardening.
3. Incorrect optical budget (ignoring connector/splice loss or using the wrong RX sensitivity).

For each: prompt used, buggy code, diagnosis (packet flow / math), corrected code,
regression test that now prevents recurrence.

---

## 10. Timeline (today 2 Nov, due 10 Nov)

| Day | Work |
|---|---|
| 1–2 | Core models, presets, physics + VLSM with tests |
| 3–4 | Routing/VLAN, rationale engine, IOS config generator |
| 5 | CLI commands, run storage, report formatters |
| 6 | Test hardening, 3 preset exports, README |
| 7 | `ai_audit_log.md`, Packet Tracer/GNS3 verification |
| 8 | Buffer: fixes, static HTML report polish, final review |

---

## 11. Risks & Decisions

- Python 3.14 wheel compatibility for Pydantic — fallback to 3.12 venv if needed.
- Scope discipline: engine correctness + explainability carry 50 of 100 points; no UI work.
- Exports must be validated in Packet Tracer/GNS3 (topology mismatch is likely if
  interfaces are assumed rather than parameterized).
- Keep one serializer for table/JSON/Markdown/HTML output to avoid drift between formats.
- If a dashboard is ever required later, the headless engine can be wrapped without
  rewriting core logic.
