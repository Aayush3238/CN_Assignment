# NetArchitect Report: metro-man

Metro MAN: HQ plus two remote sites (15-35 km), 450 users and a FinTech colo. Focus: OS2 SMF, EVPL, sub-5 ms QoS, dual-homed failover.

## Scenario

| Parameter | Value |
|---|---|
| Endpoints | 450 |
| Buildings | 1 |
| Remote sites | 2 |
| Root prefix | 10.10.0.0/16 |
| Resiliency | dual-homed |
| Cloud VPC | False |

## Layer 1 media

| Link | Distance | Media | Transceiver | Standard |
|---|---|---|---|---|
| LAN access | 90 m | Cat6a copper | 10GBASE-T | IEEE 802.3an |
| Building/site backbone | 300 m | OM4 multimode fiber | 10GBASE-SR | IEEE 802.3ae (850 nm) |
| WAN/MAN link | 22 km | OS2 single-mode fiber | 10GBASE-ER | IEEE 802.3ae (1550 nm) |

## VLAN plan

| VLAN | Name | Subnet | Gateway | Trunk allowed | PoE |
|---|---|---|---|---|---|
| 10 | Corporate | 10.10.0.0/24 | 10.10.0.1 | 10,20,30,40,50,60,999 | no |
| 20 | Trading | 10.10.1.0/25 | 10.10.1.1 | 10,20,30,40,50,60,999 | no |
| 30 | Voice | 10.10.1.128/26 | 10.10.1.129 | 10,20,30,40,50,60,999 | yes |
| 40 | Guest | 10.10.1.192/26 | 10.10.1.193 | 10,20,30,40,50,60,999 | no |
| 50 | Management | 10.10.2.32/27 | 10.10.2.33 | 10,20,30,40,50,60,999 | no |
| 60 | Colo-DMZ | 10.10.2.0/27 | 10.10.2.1 | 10,20,30,40,50,60,999 | no |

## VLSM allocation

| Name | Requested | CIDR | Wildcard | Gateway | Broadcast | Usable |
|---|---|---|---|---|---|---|
| Corporate | 200 | 10.10.0.0/24 | 0.0.0.255 | 10.10.0.1 | 10.10.0.255 | 254 |
| Trading | 120 | 10.10.1.0/25 | 0.0.0.127 | 10.10.1.1 | 10.10.1.127 | 126 |
| Voice | 50 | 10.10.1.128/26 | 0.0.0.63 | 10.10.1.129 | 10.10.1.191 | 62 |
| Guest | 40 | 10.10.1.192/26 | 0.0.0.63 | 10.10.1.193 | 10.10.1.255 | 62 |
| Colo-DMZ | 20 | 10.10.2.0/27 | 0.0.0.31 | 10.10.2.1 | 10.10.2.31 | 30 |
| Management | 18 | 10.10.2.32/27 | 0.0.0.31 | 10.10.2.33 | 10.10.2.63 | 30 |

Address-space utilisation: **0.88%** (576/65536); host utilisation: **79.43%** (448/564).

## Routing

**Multi-Area OSPF** (L3-ROUTE-02)

Selected multi-area OSPF because the design spans 2 remote site/WAN link(s) or exceeds 50 subnets. Area 0 remains the transit core, while remote areas isolate SPF churn and permit route summarisation.

| Area | Subnets |
|---|---|
| 0 | 10.10.0.0/24, 10.10.1.0/25 |
| 10 | 10.10.1.128/26, 10.10.1.192/26 |
| 20 | 10.10.2.0/27, 10.10.2.32/27 |

Summarisation commands:

- `area 10 range 10.10.1.128 255.255.255.128`
- `area 20 range 10.10.2.0 255.255.255.192`

## Explainability log

### L1-DIST-01: Cat6a copper / 10GBASE-T

*Domain:* L1  
*Condition:* 90 m on access link (requested: auto)  
*Standard:* IEEE 802.3an

> Selected Cat6a (10GBASE-T) because the 90 m run is within the 100 m limit defined by IEEE 802.3an; Cat6a sustains 10 Gbps at this distance without active optics.

### L1-DIST-02: OM4 multimode fiber / 10GBASE-SR

*Domain:* L1  
*Condition:* 300 m on backbone link (requested: auto)  
*Standard:* IEEE 802.3ae (850 nm)

> Selected OM4 Multimode Fiber (10GBASE-SR) because the 300 m run exceeds the 100 m copper limit but remains inside the 400 m OM4 reach at 850 nm, where modal dispersion and attenuation stay within budget.

### L1-DIST-03: OS2 single-mode fiber / 10GBASE-ER

*Domain:* L1  
*Condition:* 22000 m on wan link (requested: auto)  
*Standard:* IEEE 802.3ae (1550 nm)

> Selected OS2 Single-Mode Fiber because link distance (22.0 km) exceeds the 400 m attenuation limit of OM4 Multimode Fiber. Chose 10GBASE-ER (1550 nm) with a calculated link loss of 6.7 dB against a 10.5 dB budget (5.5 dB fiber + 1.0 dB connectors + 0.2 dB splices); nominal reach is 40 km.

### VLSM-ALLOC: 6 non-overlapping subnets

*Domain:* VLSM  
*Condition:* largest-first allocation with CIDR boundary alignment  
*Standard:* RFC 4632 (CIDR)

> Allocated 6 subnets from 10.10.0.0/16 using largest-first VLSM. Address-space utilisation is 0.88% and host utilisation is 79.43%.

### VLSM-BLOCK: Corporate -> 10.10.0.0/24

*Domain:* VLSM  
*Condition:* needed 200 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.10.0.0/24 to Corporate: 254 usable addresses, gateway 10.10.0.1, wildcard 0.0.0.255. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Trading -> 10.10.1.0/25

*Domain:* VLSM  
*Condition:* needed 120 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.10.1.0/25 to Trading: 126 usable addresses, gateway 10.10.1.1, wildcard 0.0.0.127. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Voice -> 10.10.1.128/26

*Domain:* VLSM  
*Condition:* needed 50 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.10.1.128/26 to Voice: 62 usable addresses, gateway 10.10.1.129, wildcard 0.0.0.63. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Guest -> 10.10.1.192/26

*Domain:* VLSM  
*Condition:* needed 40 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.10.1.192/26 to Guest: 62 usable addresses, gateway 10.10.1.193, wildcard 0.0.0.63. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Colo-DMZ -> 10.10.2.0/27

*Domain:* VLSM  
*Condition:* needed 20 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.10.2.0/27 to Colo-DMZ: 30 usable addresses, gateway 10.10.2.1, wildcard 0.0.0.31. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Management -> 10.10.2.32/27

*Domain:* VLSM  
*Condition:* needed 18 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.10.2.32/27 to Management: 30 usable addresses, gateway 10.10.2.33, wildcard 0.0.0.31. Blocks are aligned and checked for overlap with all previously allocated subnets.

### L3-ROUTE-02: Multi-Area OSPF

*Domain:* L3  
*Condition:* single-AS vs multi-site/cloud boundary  
*Standard:* RFC 2328 (OSPFv2), RFC 4271 (BGP-4)

> Selected multi-area OSPF because the design spans 2 remote site/WAN link(s) or exceeds 50 subnets. Area 0 remains the transit core, while remote areas isolate SPF churn and permit route summarisation.

### VLAN-8021Q: VLAN 10 (Corporate)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 10 (Corporate) carries HQ corporate users on 10.10.0.0/24 with gateway 10.10.0.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 20 (Trading)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 20 (Trading) carries Low-latency trading floor on 10.10.1.0/25 with gateway 10.10.1.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 30 (Voice)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 30 (Voice) carries Trading turret/voice on 10.10.1.128/26 with gateway 10.10.1.129. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated. PoE is enabled on access ports for this VLAN (802.3af/at budget planned per AP).

### VLAN-8021Q: VLAN 40 (Guest)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 40 (Guest) carries Visitor access on 10.10.1.192/26 with gateway 10.10.1.193. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 50 (Management)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 50 (Management) carries Out-of-band management on 10.10.2.32/27 with gateway 10.10.2.33. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: root (priority 4096).

### VLAN-8021Q: VLAN 60 (Colo-DMZ)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 60 (Colo-DMZ) carries FinTech colocation services on 10.10.2.0/27 with gateway 10.10.2.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### L2-RSTP: Rapid PVST+

*Domain:* L2  
*Condition:* loop prevention with deterministic root selection  
*Standard:* IEEE 802.1w

> Selected Rapid PVST+ with per-VLAN root priority 4096 on the management VLAN so that each VLAN has a deterministic root and sub-second reconvergence after a topology change.

### L2-RESILIENCY: dual-homed uplinks + HSRP/VRRP peer

*Domain:* L2  
*Condition:* scenario requires non-single-homed availability  
*Standard:* RFC 5798 (VRRP)

> Selected dual-homed design with a paired gateway peer because the scenario requests resilience beyond a single uplink. HSRP/VRRP removes the gateway as a single point of failure.

### L3-QOS: EF priority queue + CS3 signalling bandwidth

*Domain:* QoS  
*Condition:* latency-sensitive traffic on the WAN  
*Standard:* RFC 2474 / RFC 2475 (DiffServ)

> Selected a strict priority queue for DSCP EF and a reserved bandwidth class for CS3 because the scenario requires 5 ms application latency. Lower latency-sensitive traffic is shaped by class-default.

## Generated configurations

- `switches.cfg`
- `router.cfg`
- `acl.cfg`
- `qos.cfg`
