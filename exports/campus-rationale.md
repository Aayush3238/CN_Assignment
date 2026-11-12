# NetArchitect design: campus

> Campus LAN: three buildings inside 400 m, 1,600 endpoints, PoE access points, Cat6a access and OM4 backbone.

## Scenario

| Field | Value |
|---|---|
| Endpoints | 1600 |
| Buildings | 3 |
| Root prefix | 10.10.0.0/16 |
| Resilient | yes |
| Single autonomous system | yes |
| Cloud boundary | no |
| Access speed | 1 Gb/s |
| Uplinks | 2 x 10 Gb/s |

## Selected design

| Item | Selected |
|---|---|
| Topology | Three-tier (39 switches) |
| Routing | OSPF Area 0 |
| Spanning tree | RSTP |
| First-hop redundancy | HSRP |
| Address utilisation | 69.4% |
| Oversubscription | 2.4:1 |

## Media selection

| Link | Distance | Medium | Transceiver | Loss / budget | Severity |
|---|---|---|---|---|---|
| LAN access | 90 m | Cat6a copper | 10GBASE-T | - | info |
| Building backbone | 320 m | OM4 multimode fiber | 10GBASE-SR | - | info |

## Decision log

### Physical media (L1): Cat6a copper / 10GBASE-T

**Why.** Selected Cat6a copper with a 10GBASE-T transceiver because the access run (90 m) is within the 100 m 10GBASE-T channel limit (IEEE 802.3an). Category 6a supports 10 Gb/s over 100 m and is the lowest-cost medium at this distance.

**Standard.** IEEE 802.3an (10GBASE-T)

**Severity.** info

### Physical media (L1): OM4 multimode fiber / 10GBASE-SR

**Why.** Selected OM4 multimode fiber because the backbone run (320 m): it exceeds the 100 m Cat6a limit and stays inside the 400 m reach of 10GBASE-SR at 850 nm (IEEE 802.3ae). Modal dispersion limits multimode reach, so the design stays within the 400 m OM4 catalogue distance.

**Standard.** IEEE 802.3ae (10GBASE-SR)

**Severity.** info

### Addressing (VLSM): 10.10.0.0/16 -> 5 non-overlapping subnets

**Why.** Allocated 5 subnets inside 10.10.0.0/16 by sorting host requests largest-first and aligning each block to its own power-of-two boundary. 1600 requested hosts occupy 2304 addresses (69.4% address utilisation, 69.7% of usable addresses). An independent range scan confirms no overlap. Plan: Data 10.10.0.0/22, Wi-Fi 10.10.4.0/23, Voice 10.10.6.0/23, Management 10.10.8.0/25, Servers 10.10.8.128/25.

**Standard.** RFC 1918 private addressing; RFC 4632 CIDR; RFC 3021 for /31

**Severity.** info

### Topology: Three-tier (34 access, 3 distribution, 2 core)

**Why.** Selected three-tier because endpoints (1600) are >= 1000 or buildings (3) are >= 4. The design uses 34 access switch(es) at 48 ports each, 3 distribution switch(es), and 2 core switch(es). Oversubscription is (48 x 1 Gb/s) / (2 x 10 Gb/s) = 2.4:1. Cost was not scored because the scenario did not supply all three switch prices.

**Standard.** CIC-307 topology-tier rule; 48-port access switch sizing

**Severity.** info

### Routing (L3): OSPF Area 0

**Why.** Selected single-area OSPF Area 0 because the scenario has one site, one autonomous system, 5 subnets (< 50), and no inter-site link longer than 400 m. A single link-state area converges quickly and keeps the design simple (RFC 2328).

**Standard.** RFC 2328 (OSPFv2); RFC 4271 (BGP-4)

**Severity.** info

### Switching (L2): RSTP + HSRP

**Why.** RSTP (IEEE 802.1w) is sufficient: 5 VLAN(s) <= 16 and 39 switch(es) < 50. Rapid PVST+ gives sub-second convergence per VLAN and Packet Tracer accepts it directly. HSRP is configured because the scenario is resilient: two cores share a virtual gateway, the first core uses priority 110, the second 100, and preemption returns traffic after a failure. VRRP (RFC 5798) is the open alternative. Trunk hardening: allowed VLANs 10, 20, 30, 40, 50, native VLAN 999.

**Standard.** IEEE 802.1w; IEEE 802.1s; RFC 5798 (VRRP alternative)

**Severity.** info

### Security and hardening: Guest/server ACL, SSH-only VTY, and explicit trunk hardening

**Why.** The Wi-Fi/guest subnet is denied reachability to the server subnet with an extended ACL, management access is restricted to SSH from the management subnet, and trunks use an explicit allowed-VLAN list with an unused native VLAN. No IPsec policy is generated because there is no cloud or WAN boundary in this scenario.

**Standard.** Cisco IOS extended ACL syntax; IEEE 802.1Q

**Severity.** info

## Address plan

| Subnet | VLAN | CIDR | Mask | Wildcard | Gateway | Usable | Use |
|---|---|---|---|---|---|---|---|
| Data | 10 | 10.10.0.0/22 | 255.255.252.0 | 0.0.3.255 | 10.10.0.1 | 1022 | 68% |
| Wi-Fi | 30 | 10.10.4.0/23 | 255.255.254.0 | 0.0.1.255 | 10.10.4.1 | 510 | 78% |
| Voice | 20 | 10.10.6.0/23 | 255.255.254.0 | 0.0.1.255 | 10.10.6.1 | 510 | 59% |
| Management | 40 | 10.10.8.0/25 | 255.255.255.128 | 0.0.0.127 | 10.10.8.1 | 126 | 79% |
| Servers | 50 | 10.10.8.128/25 | 255.255.255.128 | 0.0.0.127 | 10.10.8.129 | 126 | 79% |

## Alternate design

| Item | Selected | Alternate |
|---|---|---|
| Topology | Three-tier | Collapsed core |
| Routing | OSPF Area 0 | Multi-area OSPF |
| Switches | 39 | 36 |
| Violations | 0 | 1 |

Alternate violations:

- Collapsed core violates the tier rule for 1600 endpoints and 3 buildings; three-tier is required at >= 1000 endpoints or >= 4 buildings.

## Generated configurations

- `campus-acc1`
- `campus-acc2`
- `campus-acc3`
- `campus-core1`
- `campus-core2`
- `campus-dist1`
- `campus-dist2`
- `campus-dist3`

The combined Packet Tracer file is `exports/campus.txt`; each device starts at a `! ===== DEVICE:` banner.

## Credentials

Lab only: enable secret and local user `admin` use `NetArchitect-Lab-123`; the IPsec pre-shared key is `NetArchitect-Lab-Key`. Replace both before any real deployment.
