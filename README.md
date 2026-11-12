# NetArchitect

**CIC-307 Computer Networks Mini-Project**  
Explainable network planning and Cisco IOS configuration engine.

NetArchitect turns a campus, metro, or global WAN scenario into:

- an explained Layer-1 medium and transceiver choice,
- a bitwise VLSM address plan with no overlaps,
- a topology tier and oversubscription calculation,
- an OSPF/BGP routing plan with area summaries,
- copy-ready Cisco IOS for switches, routers, SVIs, ACLs, QoS, and IPsec,
- a decision log that cites the input numbers and the standards behind every rule.

The CLI and the web dashboard call the same `analyze()` function. Neither one
recalculates a mask, an optical budget, or an area summary.

---

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

python -m netarchitect list-presets
python -m netarchitect explain campus
python -m netarchitect run --preset campus --out exports
python -m uvicorn netarchitect.api:app --reload
```

Open <http://127.0.0.1:8000> for the dashboard. The API documentation is at
<http://127.0.0.1:8000/docs>.

Python 3.10 or newer is required. The reference report was written with
Python 3.11; the code has no 3.11-only syntax.

---

## Presets

| Preset | Scale | Root | Design |
|---|---|---|---|
| `campus` | 1,600 endpoints, 3 buildings, 90 m access, 320 m backbone | `10.10.0.0/16` | Three-tier, RSTP, HSRP, OSPF Area 0 |
| `metro` | 450 users, HQ + 2 remote sites, 15 km and 35 km links | `10.20.0.0/16` | Collapsed core, multi-area OSPF, per-site summaries |
| `wan` | 2,000 IoT endpoints, 4 cities + cloud VPC | `10.64.0.0/14` | Three-tier, multi-area OSPF + eBGP, IPsec |

```powershell
python -m netarchitect list-presets
python -m netarchitect explain campus
python -m netarchitect explain metro --format json
python -m netarchitect explain wan --format md
```

`explain` prints the design summary, the Layer-1 table, the VLSM plan, and the
full decision log. `--format json` and `--format md` are available for reports.

---

## CLI

```powershell
# List the three scenarios
python -m netarchitect list-presets

# Explain every choice for a preset
python -m netarchitect explain campus

# Generate configs and write the export bundle
python -m netarchitect run --preset campus --out exports
python -m netarchitect run --preset metro  --out exports
python -m netarchitect run --preset wan    --out exports

# Validate a custom scenario without writing configs
python -m netarchitect validate examples/branch-office.json

# Allocate subnets without running a full scenario
python -m netarchitect vlsm 10.0.0.0/16 --hosts 500,200,100,50

# Start the dashboard (same as the uvicorn command)
python -m netarchitect serve --reload
```

`run` writes three files per preset:

```
exports/campus.txt              combined Cisco IOS, split by device banner
exports/campus-plan.json        full design object (media, VLSM, decisions, configs)
exports/campus-rationale.md     human-readable decision log
```

Exit codes: `0` success, `2` invalid input or boundary error, `3` address-space
exhaustion.

---

## Custom scenario JSON

A custom file uses the same schema as the presets. The parser rejects a blank
name, a boolean where an integer is required, a zero or non-numeric distance, a
duplicate VLAN, a reserved VLAN (1, 999, 1002-1005), a subnet claimed by two
sites, and a price block missing any of the three switch roles.

```json
{
  "name": "branch-office",
  "description": "Single branch with users, voice, guest Wi-Fi, and a WAN link.",
  "endpoints": 180,
  "buildings": 1,
  "links": [
    {"name": "Access run", "distance_m": 85, "kind": "access", "media": "copper"},
    {"name": "Branch WAN", "distance_m": 5000, "kind": "wan", "media": "fiber"}
  ],
  "root_prefix": "10.50.0.0/23",
  "subnets": [
    {"name": "Users", "hosts": 100, "vlan": 10, "site": "Branch"},
    {"name": "Voice", "hosts": 40, "vlan": 20, "site": "Branch", "poe": true},
    {"name": "Guest", "hosts": 30, "vlan": 30, "site": "Branch"},
    {"name": "WAN-Link", "hosts": 2, "mode": "p2p30", "site": "Branch", "between": ["Branch", "ISP"]}
  ],
  "sites": [
    {"name": "Branch", "subnets": ["Users", "Voice", "Guest", "WAN-Link"], "role": "hq"}
  ],
  "resilient": false,
  "single_as": true,
  "cloud": false,
  "access_speed_gbps": 1,
  "uplink_speed_gbps": 1,
  "uplinks": 1
}
```

Run it with:

```powershell
python -m netarchitect validate examples/branch-office.json
python -m netarchitect explain --input examples/branch-office.json
python -m netarchitect run --input examples/branch-office.json --out exports
```

The `validate` command takes a path, so a custom file can be named anything.

---

## Rules implemented

| Domain | Rule |
|---|---|
| Media | `<= 100 m` Cat6a / 10GBASE-T (IEEE 802.3an); `101-400 m` OM4 / 10GBASE-SR 850 nm (IEEE 802.3ae); `> 400 m` OS2 / 10GBASE-LR to 10 km, 10GBASE-ER to 40 km; `> 40 km` warns for amplification or DWDM |
| Boundary | Copper requested past 100 m raises `PhysicalDistanceViolationError` with a signal-attenuation warning; distances are never clamped |
| Optical budget | `0.35 dB/km + 0.5 dB per connector + 0.1 dB per splice + 3.0 dB margin`; LR budget 6.2 dB, ER budget 11.1 dB |
| VLSM | Sort descending, align each block to its power-of-two boundary, emit network/mask/wildcard/broadcast/gateway/usable/utilization; `/30`, `/31` (RFC 3021), `/32`; independent overlap check; exhaustion raises `AddressSpaceExhaustedError` |
| Topology | Three-tier when endpoints `>= 1000` or buildings `>= 4`; otherwise collapsed core. Access switches `ceil(endpoints / 48)`; oversubscription `(48 x access Gb/s) / (uplinks x uplink Gb/s)` |
| Routing | One AS and `< 50` subnets: OSPF Area 0. Multiple sites with a link `> 400 m`, or `>= 50` subnets: multi-area OSPF. Cloud boundary or multiple AS: multi-area OSPF + eBGP. Missing ASNs are a validation error |
| Switching | RSTP when `VLANs <= 16` and `switches < 50`; otherwise MSTP. HSRP when resilient; VRRP named as the open alternative |
| Hardening | Explicit trunk allowed-VLAN list (never `allowed vlan all`), native VLAN 999 not in the user list, PortFast + BPDU Guard, SSH-only VTY filtered by an ACL, guest-to-server deny ACL, IPsec at the cloud boundary |

---

## Dashboard

The dashboard loads a preset or overrides distance, endpoint count, building
count, and resiliency. Tabs show:

- **Overview** — selected design, alternate design, and the Layer-1 media table.
- **Decision log** — every choice with its standard, severity, and reason.
- **Address plan** — CIDR, mask, wildcard, broadcast, gateway, usable hosts, use.
- **Tier diagram** — core, distribution, and access layers with the planned count.
- **Configurations** — per-device IOS, selectable from a drop-down.

The alternate design is built from the same engine with the opposite tier and
routing mode. It is marked with violations when it breaks the tier rule or
omits the eBGP cloud boundary.

---

## Cisco Packet Tracer / GNS3 lab

Each export is a single text file split by a banner:

```
! ===== DEVICE: campus-core1 =====
```

For each device:

1. Open the device CLI, enter `enable`, then `configure terminal`.
2. Copy from the `hostname` line through `end` and paste it into the terminal.
3. Save with `write memory`.

Suggested device models from the reference lab:

| Role | Packet Tracer model |
|---|---|
| Campus core / distribution | 3560-24PS |
| Campus access | 2960-24TT |
| Metro / WAN routers | 2911 |

Interface notes:

- The 3560-24PS has `GigabitEthernet0/1` and `GigabitEthernet0/2` only. If the
  generated config names a third `GigabitEthernet`, apply that block to a free
  `FastEthernet` port and cable it there.
- A serial link needs `clock rate` on the DCE end. The generated HQ/hub side
  includes it.
- If a 2911 enumerates HWIC serial ports as `Serial0/2/0` and `Serial0/3/0`,
  change the interface name in the pasted block to the port the cable uses.
- OSPF neighbours need a short wait after line protocol comes up before
  `show ip ospf neighbor` reports `FULL`.

Verification commands:

```text
show vlan brief
show interfaces trunk
show standby brief
show ip ospf neighbor
show ip route ospf
show ip bgp summary
show crypto map
ping <gateway>
```

The campus profile has no WAN interface and no BGP, by design.

### Lab credentials

These are lab strings, not production secrets:

- enable secret / local user `admin`: `NetArchitect-Lab-123`
- IPsec pre-shared key: `NetArchitect-Lab-Key`

Replace both before any real deployment.

---

## Tests

```powershell
python -m pytest
python -m pytest --cov=netarchitect.core --cov-report=term-missing
```

The suite covers:

- media boundaries at 100, 101, 400, 401, 10,000, 40,000, and 50,000 m,
- the copper-over-100 m error and the optical-loss formula,
- VLSM sorting, alignment, exact fit, exhaustion, `/30`, `/31`, `/32`, and
  wildcard masks at `/0`, `/8`, `/24`, `/30`, `/31`, `/32`,
- a 1,000-run property test that cross-checks the allocator with Python's
  `ipaddress` module (the module is imported only in the test file),
- single-area OSPF, multi-area summaries, the eBGP ASN requirement, the
  50-subnet threshold, and the WAN cloud exclusion,
- topology thresholds, forced collapsed-core violations, oversubscription,
- RSTP/MSTP and HSRP choices, trunk VLAN ordering, native VLAN exclusion,
- IOS hardening scans (no `allowed vlan all`, no phantom WAN, unique router IDs),
- all three presets end to end, the CLI exit codes, and the dashboard routes.

Current result: **128 tests passing**.

---

## Project layout

```
netarchitect/
  cli.py                  Typer commands
  api.py                  FastAPI dashboard and JSON API
  report.py               terminal, JSON, and Markdown renderers
  core/
    spec.py               scenario parsing and validation
    ipv4.py               bitwise IPv4 helpers (no ipaddress import)
    media.py              Layer-1 media and optical budget
    vlsm.py               bitwise VLSM allocator
    topology.py           tier, switch count, oversubscription
    routing.py            OSPF areas, summaries, eBGP
    switching.py          RSTP/MSTP, HSRP/VRRP, hardening
    design.py             design() and analyze()
  configs/
    configs.py            device model and IOS builder
    templates/ios_device.j2
  presets/                campus.json, metro.json, wan.json
  web/templates/          dashboard.html
tests/                    media, VLSM, routing, topology, switching, configs, CLI, API
exports/                  generated verification bundles
examples/                 custom branch-office scenario
tools/                    report PDF generator
ai_audit_log.md           AI code audit and defence log
```

---

## AI audit

`ai_audit_log.md` records the real defects found while building this project:
a cloud prefix leaked into OSPF, an OSPF area range applied on the wrong
router, duplicate router IDs on an HSRP pair, and an initialization-order bug
in the routing engine. Each entry includes the prompt, the buggy code, the
packet-flow consequence, the fix, and the regression test that prevents it.

## Report

The generated report is `NetArchitect-Report.pdf`. To rebuild it:

```powershell
python -m pip install -e ".[report]"
python tools/generate_report.py
```

The generator reads the live engine, so the tables and numbers in the PDF match
the current code. It writes 11 pages in the reference report order: abstract,
objectives, tools, architecture, media, VLSM, routing and topology, dashboard,
Cisco IOS, tests, Packet Tracer, AI audit, how to run, conclusion, references,
and a generated configuration appendix.
