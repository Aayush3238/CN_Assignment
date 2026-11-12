# NetArchitect design: wan

> Global WAN: four cities and a cloud VPC, 2,000 IoT endpoints, multi-area OSPF plus eBGP and IPsec at the cloud boundary.

## Scenario

| Field | Value |
|---|---|
| Endpoints | 2000 |
| Buildings | 4 |
| Root prefix | 10.64.0.0/14 |
| Resilient | yes |
| Single autonomous system | no |
| Cloud boundary | yes |
| Access speed | 1 Gb/s |
| Uplinks | 2 x 10 Gb/s |

## Selected design

| Item | Selected |
|---|---|
| Topology | Three-tier (48 switches) |
| Routing | Multi-area OSPF + eBGP |
| Spanning tree | RSTP |
| First-hop redundancy | HSRP |
| Address utilisation | 78.0% |
| Oversubscription | 2.4:1 |

## Media selection

| Link | Distance | Medium | Transceiver | Loss / budget | Severity |
|---|---|---|---|---|---|
| City A LAN access | 90 m | Cat6a copper | 10GBASE-T | - | info |
| City A to City B | 650 km | OS2 single-mode fiber | 10GBASE-ER | 231.50 / 11.1 dB | warning |
| City A to City C | 1200 km | OS2 single-mode fiber | 10GBASE-ER | 424.00 / 11.1 dB | warning |
| City A to City D | 4800 km | OS2 single-mode fiber | 10GBASE-ER | 1684.00 / 11.1 dB | warning |
| City A to Cloud VPC | 250 km | OS2 single-mode fiber | 10GBASE-ER | 91.50 / 11.1 dB | warning |

## Decision log

### Physical media (L1): Cat6a copper / 10GBASE-T

**Why.** Selected Cat6a copper with a 10GBASE-T transceiver because the access run (90 m) is within the 100 m 10GBASE-T channel limit (IEEE 802.3an). Category 6a supports 10 Gb/s over 100 m and is the lowest-cost medium at this distance.

**Standard.** IEEE 802.3an (10GBASE-T)

**Severity.** info

### Physical media (L1): OS2 single-mode fiber / 10GBASE-ER

**Why.** Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (650 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 650.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 231.50 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 231.50 dB exceeds the 11.1 dB 10GBASE-ER budget.

**Standard.** IEEE 802.3ae (10GBASE-ER)

**Severity.** warning

### Physical media (L1): OS2 single-mode fiber / 10GBASE-ER

**Why.** Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (1200 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 1200.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 424.00 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 424.00 dB exceeds the 11.1 dB 10GBASE-ER budget.

**Standard.** IEEE 802.3ae (10GBASE-ER)

**Severity.** warning

### Physical media (L1): OS2 single-mode fiber / 10GBASE-ER

**Why.** Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (4800 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 4800.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 1684.00 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 1684.00 dB exceeds the 11.1 dB 10GBASE-ER budget.

**Standard.** IEEE 802.3ae (10GBASE-ER)

**Severity.** warning

### Physical media (L1): OS2 single-mode fiber / 10GBASE-ER

**Why.** Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (250 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 250.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 91.50 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 91.50 dB exceeds the 11.1 dB 10GBASE-ER budget.

**Standard.** IEEE 802.3ae (10GBASE-ER)

**Severity.** warning

### Addressing (VLSM): 10.64.0.0/14 -> 9 non-overlapping subnets

**Why.** Allocated 9 subnets inside 10.64.0.0/14 by sorting host requests largest-first and aligning each block to its own power-of-two boundary. 2208 requested hosts occupy 2832 addresses (78.0% address utilisation, 78.5% of usable addresses). An independent range scan confirms no overlap. Plan: CityA-IoT 10.64.0.0/22, CityB-IoT 10.64.4.0/23, CityC-IoT 10.64.6.0/23, CityD-IoT 10.64.8.0/23, Cloud-VPC 10.64.10.0/24, Link-A-B 10.64.11.0/30, Link-A-C 10.64.11.4/30, Link-A-D 10.64.11.8/30, Link-A-Cloud 10.64.11.12/30.

**Standard.** RFC 1918 private addressing; RFC 4632 CIDR; RFC 3021 for /31

**Severity.** info

### Topology: Three-tier (42 access, 4 distribution, 2 core)

**Why.** Selected three-tier because endpoints (2000) are >= 1000 or buildings (4) are >= 4. The design uses 42 access switch(es) at 48 ports each, 4 distribution switch(es), and 2 core switch(es). Oversubscription is (48 x 1 Gb/s) / (2 x 10 Gb/s) = 2.4:1. Cost was not scored because the scenario did not supply all three switch prices.

**Standard.** CIC-307 topology-tier rule; 48-port access switch sizing

**Severity.** info

### Routing (L3): Multi-area OSPF + eBGP

**Why.** Selected multi-area OSPF plus eBGP because the scenario contains a cloud boundary (True) or more than one autonomous system (single_as=False). OSPF Area 0 carries the internal topology with per-site areas and summaries (RFC 2328); eBGP advertises the internal prefixes to AS 64512 from AS 65010 and isolates the routing domains (RFC 4271).

**Standard.** RFC 2328 (OSPFv2); RFC 4271 (BGP-4)

**Severity.** info

### Routing (L3): Area 1 summary 10.64.4.0/23

**Why.** Area 1 (CityB) is summarised as 10.64.4.0/23, the shortest prefix covering 1 block(s), and it does not contain another site.

**Standard.** RFC 2328 area range summarisation

**Severity.** info

### Routing (L3): Area 2 summary 10.64.6.0/23

**Why.** Area 2 (CityC) is summarised as 10.64.6.0/23, the shortest prefix covering 1 block(s), and it does not contain another site.

**Standard.** RFC 2328 area range summarisation

**Severity.** info

### Routing (L3): Area 3 summary 10.64.8.0/23

**Why.** Area 3 (CityD) is summarised as 10.64.8.0/23, the shortest prefix covering 1 block(s), and it does not contain another site.

**Standard.** RFC 2328 area range summarisation

**Severity.** info

### Switching (L2): RSTP + HSRP

**Why.** RSTP (IEEE 802.1w) is sufficient: 5 VLAN(s) <= 16 and 48 switch(es) < 50. Rapid PVST+ gives sub-second convergence per VLAN and Packet Tracer accepts it directly. HSRP is configured because the scenario is resilient: two cores share a virtual gateway, the first core uses priority 110, the second 100, and preemption returns traffic after a failure. VRRP (RFC 5798) is the open alternative. Trunk hardening: allowed VLANs 10, 20, 30, 40, 50, native VLAN 999.

**Standard.** IEEE 802.1w; IEEE 802.1s; RFC 5798 (VRRP alternative)

**Severity.** info

### Security and hardening: Guest/server ACL, SSH-only VTY, site-to-site IPsec on the cloud-facing interface, and a QoS priority queue for latency-sensitive traffic

**Why.** The Wi-Fi/guest subnet is denied reachability to the server subnet with an extended ACL, management access is restricted to SSH from the management subnet, and trunks use an explicit allowed-VLAN list with an unused native VLAN. The cloud boundary adds an ISAKMP/IPsec transform and crypto map because the traffic crosses an untrusted provider.

**Standard.** RFC 4301 (IPsec); Cisco IOS extended ACL syntax

**Severity.** info

## Address plan

| Subnet | VLAN | CIDR | Mask | Wildcard | Gateway | Usable | Use |
|---|---|---|---|---|---|---|---|
| CityA-IoT | 10 | 10.64.0.0/22 | 255.255.252.0 | 0.0.3.255 | 10.64.0.1 | 1022 | 59% |
| CityB-IoT | 20 | 10.64.4.0/23 | 255.255.254.0 | 0.0.1.255 | 10.64.4.1 | 510 | 98% |
| CityC-IoT | 30 | 10.64.6.0/23 | 255.255.254.0 | 0.0.1.255 | 10.64.6.1 | 510 | 98% |
| CityD-IoT | 40 | 10.64.8.0/23 | 255.255.254.0 | 0.0.1.255 | 10.64.8.1 | 510 | 78% |
| Cloud-VPC | 50 | 10.64.10.0/24 | 255.255.255.0 | 0.0.0.255 | 10.64.10.1 | 254 | 79% |
| Link-A-B | - | 10.64.11.0/30 | 255.255.255.252 | 0.0.0.3 | 10.64.11.1 | 2 | 100% |
| Link-A-C | - | 10.64.11.4/30 | 255.255.255.252 | 0.0.0.3 | 10.64.11.5 | 2 | 100% |
| Link-A-D | - | 10.64.11.8/30 | 255.255.255.252 | 0.0.0.3 | 10.64.11.9 | 2 | 100% |
| Link-A-Cloud | - | 10.64.11.12/30 | 255.255.255.252 | 0.0.0.3 | 10.64.11.13 | 2 | 100% |

## Alternate design

| Item | Selected | Alternate |
|---|---|---|
| Topology | Three-tier | Collapsed core |
| Routing | Multi-area OSPF + eBGP | Multi-area OSPF |
| Switches | 48 | 44 |
| Violations | 4 | 6 |

Alternate violations:

- Collapsed core violates the tier rule for 2000 endpoints and 4 buildings; three-tier is required at >= 1000 endpoints or >= 4 buildings.
- Multi-area OSPF alone omits the eBGP boundary required by the cloud VPC or second autonomous system.
- City A to City B: Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (650 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 650.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 231.50 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 231.50 dB exceeds the 11.1 dB 10GBASE-ER budget.
- City A to City C: Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (1200 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 1200.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 424.00 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 424.00 dB exceeds the 11.1 dB 10GBASE-ER budget.
- City A to City D: Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (4800 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 4800.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 1684.00 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 1684.00 dB exceeds the 11.1 dB 10GBASE-ER budget.
- City A to Cloud VPC: Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (250 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 250.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 91.50 dB against a 11.1 dB budget. Warning: the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs an amplifier or DWDM; estimated loss 91.50 dB exceeds the 11.1 dB 10GBASE-ER budget.

## Generated configurations

- `wan-citya-rtr`
- `wan-citya-sw`
- `wan-cityb-rtr`
- `wan-cityb-sw`
- `wan-cityc-rtr`
- `wan-cityc-sw`
- `wan-cityd-rtr`
- `wan-cityd-sw`
- `wan-cloud-rtr`

The combined Packet Tracer file is `exports/wan.txt`; each device starts at a `! ===== DEVICE:` banner.

## Credentials

Lab only: enable secret and local user `admin` use `NetArchitect-Lab-123`; the IPsec pre-shared key is `NetArchitect-Lab-Key`. Replace both before any real deployment.
