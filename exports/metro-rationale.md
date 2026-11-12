# NetArchitect design: metro

> Metro MAN: headquarters plus two remote sites over 15 km and 35 km, OS2 single-mode, sub-5 ms QoS and dual-homed failover.

## Scenario

| Field | Value |
|---|---|
| Endpoints | 450 |
| Buildings | 3 |
| Root prefix | 10.20.0.0/16 |
| Resilient | yes |
| Single autonomous system | yes |
| Cloud boundary | no |
| Access speed | 1 Gb/s |
| Uplinks | 2 x 10 Gb/s |

## Selected design

| Item | Selected |
|---|---|
| Topology | Collapsed core (12 switches) |
| Routing | Multi-area OSPF |
| Spanning tree | RSTP |
| First-hop redundancy | HSRP |
| Address utilisation | 69.7% |
| Oversubscription | 2.4:1 |

## Media selection

| Link | Distance | Medium | Transceiver | Loss / budget | Severity |
|---|---|---|---|---|---|
| HQ LAN access | 90 m | Cat6a copper | 10GBASE-T | - | info |
| HQ to Remote A | 15 km | OS2 single-mode fiber | 10GBASE-ER | 9.25 / 11.1 dB | info |
| HQ to Remote B | 35 km | OS2 single-mode fiber | 10GBASE-ER | 16.25 / 11.1 dB | warning |

## Decision log

### Physical media (L1): Cat6a copper / 10GBASE-T

**Why.** Selected Cat6a copper with a 10GBASE-T transceiver because the access run (90 m) is within the 100 m 10GBASE-T channel limit (IEEE 802.3an). Category 6a supports 10 Gb/s over 100 m and is the lowest-cost medium at this distance.

**Standard.** IEEE 802.3an (10GBASE-T)

**Severity.** info

### Physical media (L1): OS2 single-mode fiber / 10GBASE-ER

**Why.** Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (15 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 15.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 9.25 dB against a 11.1 dB budget.

**Standard.** IEEE 802.3ae (10GBASE-ER)

**Severity.** info

### Physical media (L1): OS2 single-mode fiber / 10GBASE-ER

**Why.** Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (35 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 35.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 16.25 dB against a 11.1 dB budget. Warning: estimated loss 16.25 dB exceeds the 11.1 dB 10GBASE-ER budget.

**Standard.** IEEE 802.3ae (10GBASE-ER)

**Severity.** warning

### Addressing (VLSM): 10.20.0.0/16 -> 7 non-overlapping subnets

**Why.** Allocated 7 subnets inside 10.20.0.0/16 by sorting host requests largest-first and aligning each block to its own power-of-two boundary. 474 requested hosts occupy 680 addresses (69.7% address utilisation, 71.2% of usable addresses). An independent range scan confirms no overlap. Plan: HQ-Users 10.20.0.0/24, Trading 10.20.1.0/25, RemoteA-Users 10.20.1.128/25, RemoteB-Users 10.20.2.0/25, Colo 10.20.2.128/27, Link-HQ-RemoteA 10.20.2.160/30, Link-HQ-RemoteB 10.20.2.164/30.

**Standard.** RFC 1918 private addressing; RFC 4632 CIDR; RFC 3021 for /31

**Severity.** info

### Topology: Collapsed core (10 access, 0 distribution, 2 core)

**Why.** Selected a collapsed core because endpoints (450) are < 1000 and buildings (3) are < 4. The design uses 10 access switch(es) and 2 combined core/distribution switch(es). Oversubscription is (48 x 1 Gb/s) / (2 x 10 Gb/s) = 2.4:1. Cost was not scored because the scenario did not supply all three switch prices.

**Standard.** CIC-307 topology-tier rule; 48-port access switch sizing

**Severity.** info

### Routing (L3): Multi-area OSPF

**Why.** Selected multi-area OSPF because 3 sites and a longest link of 35000 m exceed the 400 m single-site assumption, or the plan has 7 subnets (>= 50). Area 0 is the backbone; each remote site gets its own area and a summary, so a topology change in one site does not flood the others (RFC 2328).

**Standard.** RFC 2328 (OSPFv2); RFC 4271 (BGP-4)

**Severity.** info

### Routing (L3): Area 1 summary 10.20.1.128/25

**Why.** Area 1 (RemoteA) is summarised as 10.20.1.128/25, the shortest prefix covering 1 block(s), and it does not contain another site.

**Standard.** RFC 2328 area range summarisation

**Severity.** info

### Routing (L3): Area 2 summary 10.20.2.0/25

**Why.** Area 2 (RemoteB) is summarised as 10.20.2.0/25, the shortest prefix covering 1 block(s), and it does not contain another site.

**Standard.** RFC 2328 area range summarisation

**Severity.** info

### Switching (L2): RSTP + HSRP

**Why.** RSTP (IEEE 802.1w) is sufficient: 5 VLAN(s) <= 16 and 12 switch(es) < 50. Rapid PVST+ gives sub-second convergence per VLAN and Packet Tracer accepts it directly. HSRP is configured because the scenario is resilient: two cores share a virtual gateway, the first core uses priority 110, the second 100, and preemption returns traffic after a failure. VRRP (RFC 5798) is the open alternative. Trunk hardening: allowed VLANs 10, 20, 30, 40, 50, native VLAN 999.

**Standard.** IEEE 802.1w; IEEE 802.1s; RFC 5798 (VRRP alternative)

**Severity.** info

### Security and hardening: Guest/server ACL, SSH-only VTY, and explicit trunk hardening

**Why.** The Wi-Fi/guest subnet is denied reachability to the server subnet with an extended ACL, management access is restricted to SSH from the management subnet, and trunks use an explicit allowed-VLAN list with an unused native VLAN. No IPsec policy is generated because there is no cloud or WAN boundary in this scenario.

**Standard.** Cisco IOS extended ACL syntax; IEEE 802.1Q

**Severity.** info

## Address plan

| Subnet | VLAN | CIDR | Mask | Wildcard | Gateway | Usable | Use |
|---|---|---|---|---|---|---|---|
| HQ-Users | 10 | 10.20.0.0/24 | 255.255.255.0 | 0.0.0.255 | 10.20.0.1 | 254 | 79% |
| Trading | 20 | 10.20.1.0/25 | 255.255.255.128 | 0.0.0.127 | 10.20.1.1 | 126 | 79% |
| RemoteA-Users | 30 | 10.20.1.128/25 | 255.255.255.128 | 0.0.0.127 | 10.20.1.129 | 126 | 63% |
| RemoteB-Users | 40 | 10.20.2.0/25 | 255.255.255.128 | 0.0.0.127 | 10.20.2.1 | 126 | 56% |
| Colo | 50 | 10.20.2.128/27 | 255.255.255.224 | 0.0.0.31 | 10.20.2.129 | 30 | 67% |
| Link-HQ-RemoteA | - | 10.20.2.160/30 | 255.255.255.252 | 0.0.0.3 | 10.20.2.161 | 2 | 100% |
| Link-HQ-RemoteB | - | 10.20.2.164/30 | 255.255.255.252 | 0.0.0.3 | 10.20.2.165 | 2 | 100% |

## Alternate design

| Item | Selected | Alternate |
|---|---|---|
| Topology | Collapsed core | Three-tier |
| Routing | Multi-area OSPF | OSPF Area 0 |
| Switches | 12 | 15 |
| Violations | 1 | 2 |

Alternate violations:

- Single-area OSPF ignores the multi-site rule: more than one site with a link longer than 400 m, or 50 or more subnets.
- HQ to Remote B: Selected OS2 single-mode fiber with 10GBASE-ER because the wan run (35 km) exceeds the 400 m attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and carries 10GBASE-ER at 1550 nm (IEEE 802.3ae). Optical budget: 35.00 km x 0.35 dB/km + 2 connector(s) x 0.5 dB + 0 splice(s) x 0.1 dB + 3 dB margin = 16.25 dB against a 11.1 dB budget. Warning: estimated loss 16.25 dB exceeds the 11.1 dB 10GBASE-ER budget.

## Generated configurations

- `metro-hq-rtr`
- `metro-hq-sw`
- `metro-remotea-rtr`
- `metro-remotea-sw`
- `metro-remoteb-rtr`
- `metro-remoteb-sw`

The combined Packet Tracer file is `exports/metro.txt`; each device starts at a `! ===== DEVICE:` banner.

## Credentials

Lab only: enable secret and local user `admin` use `NetArchitect-Lab-123`; the IPsec pre-shared key is `NetArchitect-Lab-Key`. Replace both before any real deployment.
