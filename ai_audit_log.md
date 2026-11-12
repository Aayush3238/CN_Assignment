# NetArchitect — AI Code Audit and Defence Log

**Course:** CIC-307 Computer Networks Mini-Project  
**Project:** NetArchitect — explainable network planning and Cisco IOS engine  
**Tool used:** generative AI code assistant (scaffolding and code generation)

## Method

The project was generated from a high-level prompt describing the CIC-307
specification. Following the academic-integrity protocol, every AI-generated
rule was treated as untrusted until it was:

1. checked against the decision table in the specification,
2. exercised through the CLI and the dashboard,
3. inspected in the exported Cisco IOS, and
4. locked down with a regression test.

Four concrete defects appeared in the generated output during that validation.
Three are networking faults (a prefix in the wrong routing domain, area ranges
on the wrong router, duplicate router IDs on an HSRP pair). One is an
initialization-order bug that stopped the engine before it could emit a config.
Each is documented below with the prompt, the buggy code, the evidence, the
packet-flow consequence, the fix, and the regression test.

---

## Fault 1 — The cloud VPC prefix leaked into OSPF

### Prompt used

> Plan OSPF areas and summaries for a WAN with four cities and a cloud VPC.
> Use eBGP at the cloud boundary.

### Buggy AI-generated code (`netarchitect/core/routing.py`, before fix)

```python
area_for_site = _site_areas(scenario) if effective_multi else {...}

networks = []
for block in block_list:
    if effective_multi and not block.point_to_point:
        site = _block_site(scenario, block)
        area = area_for_site.get(site or "", 0)   # cloud became area 4
    else:
        area = 0
    networks.append(OspfNetwork(..., area=area))

summaries = _summaries(scenario, block_list, area_for_site)
```

`_site_areas()` assigned an area number to every non-HQ site, including the
cloud site. The cloud block therefore entered the OSPF network list and the
summary list, even though the design said the cloud is an eBGP boundary.

### Evidence

The generated City A router contained:

```text
router bgp 65010
 neighbor 10.64.11.14 remote-as 64512
 network 10.64.0.0 mask 255.255.252.0
 ...
router ospf 1
 area 4 range 10.64.10.0 255.255.255.0
```

The `area 4 range` statement describes a cloud prefix that City A is supposed
to reach through eBGP and IPsec, not through OSPF.

### Technical diagnosis

This is a routing-domain isolation error, not a syntax error. The cloud VPC is
outside AS 65010. Advertising `10.64.10.0/24` into OSPF makes every city router
believe the prefix is an internal OSPF route. The BGP route to AS 64512 is then
loses the administrative-distance comparison, and the IPsec crypto map is
bypassed for that destination.

### Packet-flow analysis

Before the fix, a packet from City B (`10.64.4.0/23`) to the cloud VPC
(`10.64.10.0/24`) matches the OSPF summary and is forwarded city-to-city inside
AS 65010. It never reaches the City A cloud-facing interface, so the crypto map
is never applied and the packet is not protected. After the fix, the only route
to the cloud is the eBGP route at City A; the packet reaches City A, matches the
crypto map, and crosses the IPsec tunnel to AS 64512.

### Fix applied

The cloud site is treated as a core/backbone site (area 0) and is removed from
the OSPF network list when BGP is required:

```python
CORE_ROLES = {"hq", "core", "hub", "cloud"}

cloud_sites = {site.name.lower() for site in scenario.sites if site.role == "cloud"}
for block in block_list:
    if effective_multi and not block.point_to_point:
        site = _block_site(scenario, block)
        if bgp and site is not None and site.lower() in cloud_sites:
            continue          # cloud is advertised by eBGP, not OSPF
        area = area_for_site.get(site or "", 0)
```

`_summaries()` now skips area 0, so the cloud prefix cannot produce an
`area N range` line.

### Regression tests

```python
def test_wan_summary_does_not_cover_cloud():
    plan = design(load_preset("wan"))
    cloud = plan.vlsm.by_name("Cloud-VPC")
    assert all(summary.cidr != cloud.cidr for summary in plan.routing.summaries)

def test_wan_has_bgp_and_ipsec_on_the_cloud_boundary():
    hub = analyze(load_preset("wan")).device_configs["wan-citya-rtr"]
    assert "router bgp 65010" in hub
    assert "crypto map WAN-MAP" in hub
```

---

## Fault 2 — OSPF area ranges were applied on the wrong router

### Prompt used

> Add one summary per remote site so the HQ router does not carry every remote
> subnet in its link-state database.

### Buggy AI-generated code (`netarchitect/configs/configs.py`, before fix)

```python
ranges = [
    (summary.area, summary.network, summary.mask)
    for summary in plan.routing.summaries
    if not summary.exact
]
devices.append(DeviceConfig(
    hostname="metro-hq-rtr",
    ...
    ospf=OspfDef(1, mgmt.gateway, hub_networks, hub_passive, ranges),
))
```

The generator put every summary on the HQ router. In this topology the HQ
router has interfaces only in area 0; the remote routers are the ABRs because
each one has a LAN interface in its own area and a serial interface in area 0.

### Evidence

The exported `metro-hq-rtr` block contained:

```text
router ospf 1
 router-id 10.20.0.1
 area 1 range 10.20.1.128 255.255.255.128
 area 2 range 10.20.2.0 255.255.255.128
```

The same HQ router has no `network ... area 1` or `network ... area 2`
statement. The two statements are therefore attached to a router that is not
an ABR for those areas.

### Technical diagnosis

Cisco IOS only originates an inter-area summary for an area the router is
attached to. A range configured on a non-ABR is ineffective at best and, when
the same widened prefix is configured in two areas, it can be installed as the
wrong inter-area route. The reference report records exactly this failure: a
widened `10.20.0.0/22` was advertised by both area 1 and area 3, so a packet
from Remote B toward HQ could match area 3's summary and be sent back into area
3.

### Packet-flow analysis

Before the fix, Remote B (`10.20.2.0/25`) sends a packet to HQ
(`10.20.0.0/24`). The packet reaches Remote B's ABR. If another area advertises
a cover that includes Remote B's own block, the router can prefer that
inter-area route and forward the packet back into the area it came from. The
result is a routing loop until the TTL expires.

After the fix, Remote B's own router advertises only Remote B's exact prefix or
its own shortest cover. The HQ router receives one summary per remote area from
the correct ABR, and the packet follows Remote B -> area 0 -> HQ.

### Fix applied

Each remote router now carries the ranges for its own site:

```python
ranges = [
    (summary.area, summary.network, summary.mask)
    for summary in plan.routing.summaries
    if summary.site.lower() == site.name.lower() and not summary.exact
]
```

The HQ `OspfDef` passes an empty range list.

### Regression test

```python
def test_metro_hq_has_qos_and_remote_routers_have_area_ranges():
    hq = analyze(load_preset("metro")).device_configs["metro-hq-rtr"]
    remote_a = analyze(load_preset("metro")).device_configs["metro-remotea-rtr"]
    assert "area 1 range 10.20.1.128 255.255.255.128" in remote_a
    assert "area 1 range" not in hq
```

---

## Fault 3 — Both HSRP cores used the same OSPF router ID

### Prompt used

> Generate two Layer-3 campus cores with HSRP on every VLAN and a single-area
> OSPF process.

### Buggy AI-generated code (`netarchitect/configs/configs.py`, before fix)

```python
for index in range(core_count):
    ...
    devices.append(DeviceConfig(
        hostname=f"{scenario.name}-core{index + 1}",
        ...
        ospf=OspfDef(1, mgmt.gateway, networks, passive, []),
    ))
```

`mgmt.gateway` is the same value for both cores, so both configs were rendered
with `router-id 10.10.8.1`.

### Evidence

Both `campus-core1` and `campus-core2` contained:

```text
router ospf 1
 router-id 10.10.8.1
```

### Technical diagnosis

An OSPF router ID must be unique inside an area. Two neighbours that present the
same router ID reject each other's hello packets, so the adjacency never reaches
`FULL`. HSRP can still show `Active/Standby`, which makes the fault easy to
miss: the first-hop gateway works, but the cores never exchange routes.

### Packet-flow analysis

A PC in VLAN 10 sends to the HSRP virtual gateway `10.10.0.1` on core 1. Core 1
has no OSPF route to the voice, Wi-Fi, or server VLANs because its adjacency
with core 2 never formed. The packet is dropped or follows a default route out
of the campus instead of crossing the core. After the fix, both cores form a
`FULL` adjacency and the inter-VLAN route is present in `show ip route ospf`.

### Fix applied

Each core uses its own SVI address as the router ID:

```python
router_id = _ip(mgmt, 2 + index) if scenario.resilient else mgmt.gateway
ospf=OspfDef(1, router_id, networks, passive, [])
```

Core 1 becomes `10.10.8.2`, core 2 becomes `10.10.8.3`.

### Regression test

```python
def test_campus_core1_and_core2_have_unique_router_ids_and_hsrp_priorities():
    core1 = analyze(load_preset("campus")).device_configs["campus-core1"]
    core2 = analyze(load_preset("campus")).device_configs["campus-core2"]
    assert "router-id 10.10.8.2" in core1
    assert "router-id 10.10.8.3" in core2
    assert "standby 10 priority 110" in core1
    assert "standby 10 priority 100" in core2
```

---

## Fault 4 — `bgp` was read before it was assigned

### Prompt used

> Exclude the cloud VPC from the OSPF network list when the design uses eBGP.

### Buggy AI-generated code (`netarchitect/core/routing.py`, before fix)

```python
networks = []
for block in block_list:
    if effective_multi and not block.point_to_point:
        site = _block_site(scenario, block)
        if bgp and site is not None and site.lower() in cloud_sites:
            continue
        area = area_for_site.get(site or "", 0)
    ...
    networks.append(...)

summaries = _summaries(scenario, block_list, area_for_site)
bgp = protocol.endswith("+ eBGP")      # too late
```

The cloud filter was added above the assignment that defines `bgp`.

### Evidence

Running any multi-area preset crashed before rendering:

```text
UnboundLocalError: cannot access local variable 'bgp' where it is not
associated with a value
```

The traceback pointed at `routing.py`, line 312, inside `decide_routing`.

### Technical diagnosis

Python decides that `bgp` is a local variable because it is assigned later in
the same function. Reading it before that assignment raises `UnboundLocalError`.
The engine never reached the config generator, so the failure is a hard stop
rather than a bad packet path. This is a classic AI generation mistake: a new
condition was inserted above the setup line that makes it meaningful.

### Packet-flow analysis

No packet flow existed: `analyze()` raised before any IOS file was written. The
engineering consequence is that a WAN plan with a cloud boundary could not be
generated at all. After the fix, the WAN export is produced and the cloud
prefix follows the BGP path described in Fault 1.

### Fix applied

`bgp` is computed immediately after the protocol is selected, before the
network loop:

```python
effective_multi = protocol != "OSPF Area 0"
bgp = protocol.endswith("+ eBGP")
area_for_site = _site_areas(scenario) if effective_multi else {...}
```

### Regression tests

All three presets run end to end, including the multi-area Metro plan and the
BGP WAN plan:

```python
@pytest.mark.parametrize("preset", ["campus", "metro", "wan"])
def test_preset_analyzes_end_to_end(preset):
    analysis = analyze(load_preset(preset))
    assert analysis.device_configs
```

---

## Patterns checked on purpose

The following patterns were inspected even though they did not become faults in
the final code:

| Pattern | Check |
|---|---|
| Wildcard copied from the subnet mask | OSPF network statements always use `0.0.x.x` wildcards; area ranges and BGP network statements use the subnet mask |
| VLSM alignment wrapping to `0.0.0.0` | The allocator raises `AddressSpaceExhaustedError` before the cursor can pass `255.255.255.255` |
| Trunk with no allowed-VLAN list | Every trunk emits an explicit sorted list; `switchport trunk allowed vlan all` never appears |
| Native VLAN in the user list | Native VLAN 999 is checked against every assigned VLAN and is not in the allowed list |
| OSPF network statement given a subnet mask | Tests assert wildcard != mask for every network |
| Optical budget without connector, splice, or margin | `optical_loss()` includes 0.5 dB per connector, 0.1 dB per splice, and 3.0 dB margin |
| Duplicate OSPF router ID | Campus cores now use their own SVI addresses |
| Area range on a non-ABR | Ranges are emitted only on the router that owns the site LAN |

## Validation after the fixes

```text
python -m pytest
128 passed
```

All three presets generate a complete export, the campus design has no WAN
interface or BGP, the Metro ranges appear only on the remote ABRs, and the WAN
cloud prefix is carried by eBGP and protected by IPsec.

## Summary

| # | Fault | Location | Impact | Fix | Regression test |
|---|---|---|---|---|---|
| 1 | Cloud VPC advertised into OSPF | `core/routing.py` | Cloud traffic bypasses eBGP and the IPsec crypto map | Treat cloud as area 0 and skip it in OSPF when BGP is used | `test_wan_summary_does_not_cover_cloud` |
| 2 | Area ranges on the HQ router, not the ABRs | `configs/configs.py` | Wrong inter-area summary; traffic can loop back into its own area | Emit each site's range only on that site's router | `test_metro_hq_has_qos_and_remote_routers_have_area_ranges` |
| 3 | Duplicate OSPF router ID on the HSRP pair | `configs/configs.py` | Cores never reach `FULL`; inter-VLAN routing fails | Use each core's own SVI address | `test_campus_core1_and_core2_have_unique_router_ids_and_hsrp_priorities` |
| 4 | `bgp` used before assignment | `core/routing.py` | `analyze()` crashes before writing configs | Compute `bgp` before the network loop | `test_preset_analyzes_end_to_end` |
