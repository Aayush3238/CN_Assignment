# NetArchitect

CLI-only network architecture recommendation and configuration engine for the
CIC-307 mini-project. It ingests preset or custom enterprise parameters, applies
distance/VLSM/routing rules, and emits Cisco IOS configurations plus a
natural-language justification for every decision.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

netarchitect presets list
netarchitect plan --preset campus-lan
netarchitect plan --input my-scenario.json --format md --out report.md
netarchitect vlsm 10.0.0.0/16 --hosts 500,200,100,50
netarchitect runs list
netarchitect export 1 --out exports/run-1
```

After a run, `exports/run-1/` contains the IOS configs, `rationale.md`,
`run.json`, and a self-contained `report.html` (open it in any browser; no
server required). You can also generate the HTML directly:

```powershell
netarchitect plan --preset metro-man --format html
```

## Custom scenario JSON

```json
{
  "profile": "branch-office",
  "description": "Small branch with guest Wi-Fi",
  "endpoints": 120,
  "access_distance_m": 90,
  "backbone_distance_m": 250,
  "root_prefix": "10.50.0.0/24",
  "vlans": [
    {"name": "Staff", "hosts": 60, "vlan_id": 10},
    {"name": "Guest", "hosts": 40, "vlan_id": 20},
    {"name": "Management", "hosts": 10, "vlan_id": 30}
  ]
}
```

Validate it first:

```powershell
netarchitect validate my-scenario.json
```

## Presets

| Name | Scale | Focus |
|---|---|---|
| `campus-lan` | 3 buildings, <400 m, 1,600 endpoints | Cat6a/OM4, VLANs, RSTP, single-area OSPF |
| `metro-man` | HQ + 2 remote sites, 15-35 km, 450 users | OS2 SMF/ER, QoS, dual-homed failover |
| `global-wan` | 4 cities + cloud VPC, 2,000 devices | IPsec, multi-area OSPF + eBGP, summarisation |

## Rule engine

- **L1 media**: <=100 m Cat6a/10GBASE-T; 101-400 m OM4/10GBASE-SR; >400 m OS2
  with 10GBASE-LR or ER. Copper requests beyond 100 m raise
  `PhysicalDistanceViolationError`. Single-mode links are also checked against a
  simplified optical power budget.
- **VLSM**: requests sorted largest-first, aligned bitwise, non-overlapping,
  with broadcast/gateway/wildcard/utilisation output. `/31` (RFC 3021) and
  `/32` are supported.
- **Routing**: <50 subnets in one AS -> single-area OSPF; multi-site -> multi-area
  OSPF; cloud VPC -> multi-area OSPF + eBGP.
- **L2**: explicit trunk allowed lists, unused native VLAN 999, RSTP root
  selection, PoE budgeting.
- **Explainability**: every decision is a structured record
  (`rule_id`, inputs, condition, choice, rationale, standard) included in the
  CLI output, JSON, Markdown, and HTML exports.

## Project layout

```
netarchitect/
  core/          # models, presets, physics, vlsm, routing, vlan, explain, engine
  configs/ios.py # Cisco IOS generator
  cli.py         # Typer commands
  report.py      # table/JSON/Markdown/HTML renderers
  storage.py     # SQLite run history + export bundles
tests/
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

The suite covers media boundaries (99/100/101/400/401 m), copper violations,
optical budgets, VLSM overlap/exhaustion/`/31`/`/32`, wildcard masks, routing
thresholds, generated configs, presets, and CLI exit codes.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 2 | Validation, boundary, or configuration error |
| 3 | Address-space exhaustion |
