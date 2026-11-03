# NetArchitect Report: campus-lan

Campus LAN: 3 buildings within 400 m, 1,600 endpoints and PoE access points. Focus: Cat6a/MMF, 802.1Q VLANs, RSTP, single-area OSPF.

## Scenario

| Parameter | Value |
|---|---|
| Endpoints | 1600 |
| Buildings | 3 |
| Remote sites | 0 |
| Root prefix | 10.0.0.0/16 |
| Resiliency | dual-uplink |
| Cloud VPC | False |

## Layer 1 media

| Link | Distance | Media | Transceiver | Standard |
|---|---|---|---|---|
| LAN access | 90 m | Cat6a copper | 10GBASE-T | IEEE 802.3an |
| Building/site backbone | 350 m | OM4 multimode fiber | 10GBASE-SR | IEEE 802.3ae (850 nm) |

## VLAN plan

| VLAN | Name | Subnet | Gateway | Trunk allowed | PoE |
|---|---|---|---|---|---|
| 10 | Staff | 10.0.4.0/23 | 10.0.4.1 | 10,20,30,40,50,60,999 | no |
| 20 | Students | 10.0.0.0/22 | 10.0.0.1 | 10,20,30,40,50,60,999 | no |
| 30 | Voice | 10.0.6.0/24 | 10.0.6.1 | 10,20,30,40,50,60,999 | yes |
| 40 | Guest | 10.0.7.0/25 | 10.0.7.1 | 10,20,30,40,50,60,999 | no |
| 50 | IoT | 10.0.7.128/26 | 10.0.7.129 | 10,20,30,40,50,60,999 | no |
| 60 | Management | 10.0.7.192/27 | 10.0.7.193 | 10,20,30,40,50,60,999 | no |

## VLSM allocation

| Name | Requested | CIDR | Wildcard | Gateway | Broadcast | Usable |
|---|---|---|---|---|---|---|
| Students | 700 | 10.0.0.0/22 | 0.0.3.255 | 10.0.0.1 | 10.0.3.255 | 1022 |
| Staff | 400 | 10.0.4.0/23 | 0.0.1.255 | 10.0.4.1 | 10.0.5.255 | 510 |
| Voice | 250 | 10.0.6.0/24 | 0.0.0.255 | 10.0.6.1 | 10.0.6.255 | 254 |
| Guest | 100 | 10.0.7.0/25 | 0.0.0.127 | 10.0.7.1 | 10.0.7.127 | 126 |
| IoT | 50 | 10.0.7.128/26 | 0.0.0.63 | 10.0.7.129 | 10.0.7.191 | 62 |
| Management | 20 | 10.0.7.192/27 | 0.0.0.31 | 10.0.7.193 | 10.0.7.223 | 30 |

Address-space utilisation: **3.08%** (2016/65536); host utilisation: **75.85%** (1520/2004).

## Routing

**OSPF Area 0 (single area)** (L3-ROUTE-01)

Selected single-area OSPF (Area 0) because the scenario contains 6 subnet(s), fewer than 50, inside one autonomous system. Link-state convergence is fast and the flat area keeps the design simple to operate.

| Area | Subnets |
|---|---|
| 0 | 10.0.0.0/22, 10.0.4.0/23, 10.0.6.0/24, 10.0.7.0/25, 10.0.7.128/26, 10.0.7.192/27 |

## Explainability log

### L1-DIST-01: Cat6a copper / 10GBASE-T

*Domain:* L1  
*Condition:* 90 m on access link (requested: auto)  
*Standard:* IEEE 802.3an

> Selected Cat6a (10GBASE-T) because the 90 m run is within the 100 m limit defined by IEEE 802.3an; Cat6a sustains 10 Gbps at this distance without active optics.

### L1-DIST-02: OM4 multimode fiber / 10GBASE-SR

*Domain:* L1  
*Condition:* 350 m on backbone link (requested: auto)  
*Standard:* IEEE 802.3ae (850 nm)

> Selected OM4 Multimode Fiber (10GBASE-SR) because the 350 m run exceeds the 100 m copper limit but remains inside the 400 m OM4 reach at 850 nm, where modal dispersion and attenuation stay within budget.

### VLSM-ALLOC: 6 non-overlapping subnets

*Domain:* VLSM  
*Condition:* largest-first allocation with CIDR boundary alignment  
*Standard:* RFC 4632 (CIDR)

> Allocated 6 subnets from 10.0.0.0/16 using largest-first VLSM. Address-space utilisation is 3.08% and host utilisation is 75.85%.

### VLSM-BLOCK: Students -> 10.0.0.0/22

*Domain:* VLSM  
*Condition:* needed 700 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.0.0.0/22 to Students: 1022 usable addresses, gateway 10.0.0.1, wildcard 0.0.3.255. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Staff -> 10.0.4.0/23

*Domain:* VLSM  
*Condition:* needed 400 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.0.4.0/23 to Staff: 510 usable addresses, gateway 10.0.4.1, wildcard 0.0.1.255. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Voice -> 10.0.6.0/24

*Domain:* VLSM  
*Condition:* needed 250 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.0.6.0/24 to Voice: 254 usable addresses, gateway 10.0.6.1, wildcard 0.0.0.255. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Guest -> 10.0.7.0/25

*Domain:* VLSM  
*Condition:* needed 100 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.0.7.0/25 to Guest: 126 usable addresses, gateway 10.0.7.1, wildcard 0.0.0.127. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: IoT -> 10.0.7.128/26

*Domain:* VLSM  
*Condition:* needed 50 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.0.7.128/26 to IoT: 62 usable addresses, gateway 10.0.7.129, wildcard 0.0.0.63. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Management -> 10.0.7.192/27

*Domain:* VLSM  
*Condition:* needed 20 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.0.7.192/27 to Management: 30 usable addresses, gateway 10.0.7.193, wildcard 0.0.0.31. Blocks are aligned and checked for overlap with all previously allocated subnets.

### L3-ROUTE-01: OSPF Area 0 (single area)

*Domain:* L3  
*Condition:* single-AS vs multi-site/cloud boundary  
*Standard:* RFC 2328 (OSPFv2), RFC 4271 (BGP-4)

> Selected single-area OSPF (Area 0) because the scenario contains 6 subnet(s), fewer than 50, inside one autonomous system. Link-state convergence is fast and the flat area keeps the design simple to operate.

### VLAN-8021Q: VLAN 10 (Staff)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 10 (Staff) carries Employee wired/wireless on 10.0.4.0/23 with gateway 10.0.4.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 20 (Students)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 20 (Students) carries Student devices on 10.0.0.0/22 with gateway 10.0.0.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 30 (Voice)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 30 (Voice) carries VoIP handsets on 10.0.6.0/24 with gateway 10.0.6.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated. PoE is enabled on access ports for this VLAN (802.3af/at budget planned per AP).

### VLAN-8021Q: VLAN 40 (Guest)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 40 (Guest) carries Untrusted guest Wi-Fi on 10.0.7.0/25 with gateway 10.0.7.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 50 (IoT)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 50 (IoT) carries Building sensors on 10.0.7.128/26 with gateway 10.0.7.129. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 60 (Management)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 60 (Management) carries Infrastructure management on 10.0.7.192/27 with gateway 10.0.7.193. Trunks permit only VLANs 10, 20, 30, 40, 50, 60, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: root (priority 4096).

### L2-RSTP: Rapid PVST+

*Domain:* L2  
*Condition:* loop prevention with deterministic root selection  
*Standard:* IEEE 802.1w

> Selected Rapid PVST+ with per-VLAN root priority 4096 on the management VLAN so that each VLAN has a deterministic root and sub-second reconvergence after a topology change.

### L2-RESILIENCY: dual-uplink uplinks + HSRP/VRRP peer

*Domain:* L2  
*Condition:* scenario requires non-single-homed availability  
*Standard:* RFC 5798 (VRRP)

> Selected dual-uplink design with a paired gateway peer because the scenario requests resilience beyond a single uplink. HSRP/VRRP removes the gateway as a single point of failure.

## Generated configurations

- `switches.cfg`
- `router.cfg`
- `acl.cfg`
