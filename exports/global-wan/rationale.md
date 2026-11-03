# NetArchitect Report: global-wan

Global WAN: four cities plus a cloud VPC, 2,000 IoT/scanner devices. Focus: IPsec VPN, multi-area OSPF/BGP, route summarization.

## Scenario

| Parameter | Value |
|---|---|
| Endpoints | 2000 |
| Buildings | 0 |
| Remote sites | 4 |
| Root prefix | 10.20.0.0/16 |
| Resiliency | dual-homed |
| Cloud VPC | True |

## Layer 1 media

| Link | Distance | Media | Transceiver | Standard |
|---|---|---|---|---|
| LAN access | 90 m | Cat6a copper | 10GBASE-T | IEEE 802.3an |
| WAN/MAN link | 5000 km | ISP Carrier Ethernet + IPsec VPN | N/A (service handoff) | RFC 4301 (IPsec) |

## VLAN plan

| VLAN | Name | Subnet | Gateway | Trunk allowed | PoE |
|---|---|---|---|---|---|
| 10 | IoT | 10.20.0.0/21 | 10.20.0.1 | 10,20,30,40,50,999 | no |
| 20 | Scanners | 10.20.8.0/23 | 10.20.8.1 | 10,20,30,40,50,999 | no |
| 30 | Corporate | 10.20.10.0/24 | 10.20.10.1 | 10,20,30,40,50,999 | no |
| 40 | Management | 10.20.11.0/25 | 10.20.11.1 | 10,20,30,40,50,999 | no |
| 50 | Guest | 10.20.11.128/27 | 10.20.11.129 | 10,20,30,40,50,999 | no |

## VLSM allocation

| Name | Requested | CIDR | Wildcard | Gateway | Broadcast | Usable |
|---|---|---|---|---|---|---|
| IoT | 1200 | 10.20.0.0/21 | 0.0.7.255 | 10.20.0.1 | 10.20.7.255 | 2046 |
| Scanners | 500 | 10.20.8.0/23 | 0.0.1.255 | 10.20.8.1 | 10.20.9.255 | 510 |
| Corporate | 200 | 10.20.10.0/24 | 0.0.0.255 | 10.20.10.1 | 10.20.10.255 | 254 |
| Management | 80 | 10.20.11.0/25 | 0.0.0.127 | 10.20.11.1 | 10.20.11.127 | 126 |
| Guest | 20 | 10.20.11.128/27 | 0.0.0.31 | 10.20.11.129 | 10.20.11.159 | 30 |

Address-space utilisation: **4.54%** (2976/65536); host utilisation: **67.43%** (2000/2966).

## Routing

**Multi-Area OSPF + eBGP (cloud boundary)** (L3-ROUTE-03)

Selected multi-area OSPF inside the enterprise and eBGP at the cloud VPC boundary because the design includes a cloud VPC plus 4 remote site(s). eBGP provides routing-domain isolation and policy control, while OSPF areas contain internal topology changes and allow summarisation.

| Area | Subnets |
|---|---|
| 0 | 10.20.0.0/21, 10.20.8.0/23 |
| 10 | 10.20.10.0/24, 10.20.11.0/25 |
| 20 | 10.20.11.128/27 |

## Explainability log

### L1-DIST-01: Cat6a copper / 10GBASE-T

*Domain:* L1  
*Condition:* 90 m on access link (requested: auto)  
*Standard:* IEEE 802.3an

> Selected Cat6a (10GBASE-T) because the 90 m run is within the 100 m limit defined by IEEE 802.3an; Cat6a sustains 10 Gbps at this distance without active optics.

### L1-WAN-CARRIER: ISP Carrier Ethernet + IPsec VPN / N/A (service handoff)

*Domain:* L1  
*Condition:* 5e+06 m on wan link (requested: auto)  
*Standard:* RFC 4301 (IPsec)

> Selected an ISP Carrier Ethernet handoff protected by IPsec because the 5000.0 km multi-city path cannot be served by a direct single-mode run at acceptable cost. The carrier provides the L1 transport and the enterprise overlay provides confidentiality and route isolation across the public WAN.

### VLSM-ALLOC: 5 non-overlapping subnets

*Domain:* VLSM  
*Condition:* largest-first allocation with CIDR boundary alignment  
*Standard:* RFC 4632 (CIDR)

> Allocated 5 subnets from 10.20.0.0/16 using largest-first VLSM. Address-space utilisation is 4.54% and host utilisation is 67.43%.

### VLSM-BLOCK: IoT -> 10.20.0.0/21

*Domain:* VLSM  
*Condition:* needed 1200 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.20.0.0/21 to IoT: 2046 usable addresses, gateway 10.20.0.1, wildcard 0.0.7.255. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Scanners -> 10.20.8.0/23

*Domain:* VLSM  
*Condition:* needed 500 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.20.8.0/23 to Scanners: 510 usable addresses, gateway 10.20.8.1, wildcard 0.0.1.255. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Corporate -> 10.20.10.0/24

*Domain:* VLSM  
*Condition:* needed 200 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.20.10.0/24 to Corporate: 254 usable addresses, gateway 10.20.10.1, wildcard 0.0.0.255. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Management -> 10.20.11.0/25

*Domain:* VLSM  
*Condition:* needed 80 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.20.11.0/25 to Management: 126 usable addresses, gateway 10.20.11.1, wildcard 0.0.0.127. Blocks are aligned and checked for overlap with all previously allocated subnets.

### VLSM-BLOCK: Guest -> 10.20.11.128/27

*Domain:* VLSM  
*Condition:* needed 20 usable host(s) plus network/broadcast  
*Standard:* RFC 4632 (CIDR)

> Allocated 10.20.11.128/27 to Guest: 30 usable addresses, gateway 10.20.11.129, wildcard 0.0.0.31. Blocks are aligned and checked for overlap with all previously allocated subnets.

### L3-ROUTE-03: Multi-Area OSPF + eBGP (cloud boundary)

*Domain:* L3  
*Condition:* single-AS vs multi-site/cloud boundary  
*Standard:* RFC 2328 (OSPFv2), RFC 4271 (BGP-4)

> Selected multi-area OSPF inside the enterprise and eBGP at the cloud VPC boundary because the design includes a cloud VPC plus 4 remote site(s). eBGP provides routing-domain isolation and policy control, while OSPF areas contain internal topology changes and allow summarisation.

### VLAN-8021Q: VLAN 10 (IoT)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 10 (IoT) carries Warehouse sensors on 10.20.0.0/21 with gateway 10.20.0.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 20 (Scanners)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 20 (Scanners) carries Handheld scanners on 10.20.8.0/23 with gateway 10.20.8.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 30 (Corporate)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 30 (Corporate) carries City office users on 10.20.10.0/24 with gateway 10.20.10.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

### VLAN-8021Q: VLAN 40 (Management)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 40 (Management) carries Infrastructure management on 10.20.11.0/25 with gateway 10.20.11.1. Trunks permit only VLANs 10, 20, 30, 40, 50, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: root (priority 4096).

### VLAN-8021Q: VLAN 50 (Guest)

*Domain:* L2  
*Condition:* segmentation by function with explicit trunk policy  
*Standard:* IEEE 802.1Q

> VLAN 50 (Guest) carries Visitor access on 10.20.11.128/27 with gateway 10.20.11.129. Trunks permit only VLANs 10, 20, 30, 40, 50, 999; native VLAN 999 is reserved and unused to prevent double-tagged VLAN hopping. RSTP role: designated.

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

> Selected a strict priority queue for DSCP EF and a reserved bandwidth class for CS3 because the scenario requires 150 ms application latency. Lower latency-sensitive traffic is shaped by class-default.

### L3-VPN: IPsec tunnel (AES-256/SHA-256)

*Domain:* Security  
*Condition:* traffic crosses an untrusted public WAN  
*Standard:* RFC 4301 (IPsec)

> Selected an IPsec VPN overlay because the WAN crosses public infrastructure. AES-256/SHA-256 provides confidentiality and integrity, and the tunnel policy limits interesting traffic to the enterprise/cloud prefixes.

## Generated configurations

- `switches.cfg`
- `router.cfg`
- `acl.cfg`
- `qos.cfg`
- `vpn.cfg`
