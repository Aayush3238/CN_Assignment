"""Bitwise VLSM allocator.

Algorithm:
1. Parse the root prefix.
2. Sort requests descending by host count (largest block first).
3. Walk the address space with an integer cursor, aligning each block to its
   natural boundary so no two subnets can overlap.
4. Emit network/mask/wildcard/broadcast/gateway metadata and utilisation stats.

The allocator uses :mod:`ipaddress` for the actual math, but an independent
bitwise overlap check is run afterwards as a safety net and is also exercised
by the unit tests.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from netarchitect.core.errors import AddressSpaceExhaustedError, OverlapError
from netarchitect.core.models import Subnet, Utilization, VLSMAllocation


@dataclass(frozen=True)
class VLSMRequest:
    """One subnet request passed to the allocator."""

    name: str
    hosts: int
    point_to_point: bool = False


def prefix_for_hosts(hosts: int, point_to_point: bool = False) -> int:
    """Return the smallest prefix that can hold ``hosts`` usable addresses.

    Special cases:
    * /32 for a single host (loopback or host route)
    * /31 for an explicit point-to-point link (RFC 3021)
    * otherwise reserve two addresses for network + broadcast
    """
    if point_to_point:
        if hosts > 2:
            raise ValueError("point-to-point links support at most 2 addresses")
        return 31
    if hosts < 1:
        raise ValueError("host count must be at least 1")
    if hosts == 1:
        return 32

    required = hosts + 2  # network + broadcast
    host_bits = (required - 1).bit_length()  # ceil(log2(required))
    prefix = 32 - host_bits
    if prefix < 0:
        raise ValueError(f"host count {hosts} is too large for IPv4")
    return prefix


def wildcard_mask(prefix: int) -> str:
    """Return the Cisco wildcard mask for a prefix length."""
    if not 0 <= prefix <= 32:
        raise ValueError("prefix length must be between 0 and 32")
    return str(ipaddress.ip_network(f"0.0.0.0/{prefix}").hostmask)


def _assert_no_overlap(subnets: list[Subnet]) -> None:
    """Independently verify that no two allocated blocks overlap."""
    ranges = []
    for subnet in subnets:
        network = ipaddress.ip_network(subnet.cidr)
        ranges.append((int(network.network_address), int(network.broadcast_address)))

    ranges.sort()
    for (start_a, end_a), (start_b, end_b) in zip(ranges, ranges[1:]):
        if start_b <= end_a:
            raise OverlapError(
                f"internal allocator bug: overlap detected between blocks ending at "
                f"{ipaddress.IPv4Address(end_a)} and starting at "
                f"{ipaddress.IPv4Address(start_b)}"
            )


def allocate_vlsm(root_prefix: str, requests: list[VLSMRequest]) -> VLSMAllocation:
    """Allocate non-overlapping subnets from ``root_prefix``.

    Raises:
        ValueError: malformed root prefix or duplicate names.
        AddressSpaceExhaustedError: when the requested blocks do not fit.
        OverlapError: if the safety check detects an internal bug.
    """
    if not requests:
        raise ValueError("at least one subnet request is required")

    try:
        root = ipaddress.ip_network(root_prefix, strict=False)
    except ValueError as exc:
        raise ValueError(f"invalid root prefix: {root_prefix}") from exc
    if root.version != 4:
        raise ValueError("only IPv4 prefixes are supported")
    if root.prefixlen > 30:
        raise ValueError("root prefix must be /30 or larger")

    names = [request.name.lower() for request in requests]
    if len(names) != len(set(names)):
        raise ValueError("subnet request names must be unique")

    # Stable sort: largest first; ties keep the user's original order.
    ordered = sorted(
        enumerate(requests),
        key=lambda pair: (-pair[1].hosts, pair[0]),
    )

    root_start = int(root.network_address)
    root_end_exclusive = root_start + root.num_addresses
    cursor = root_start

    allocated: list[Subnet] = []
    allocated_addresses = 0

    for _, request in ordered:
        prefix = prefix_for_hosts(request.hosts, request.point_to_point)
        block_size = 1 << (32 - prefix)

        # Align the cursor upwards to this block's natural boundary.
        aligned = ((cursor + block_size - 1) // block_size) * block_size
        block_end_exclusive = aligned + block_size
        if block_end_exclusive > root_end_exclusive:
            raise AddressSpaceExhaustedError(
                f"cannot allocate {request.name} ({request.hosts} hosts, /{prefix}) "
                f"inside {root}: address space exhausted after "
                f"{len(allocated)} subnets"
            )

        network = ipaddress.IPv4Network((aligned, prefix))

        # /32 has no network/broadcast split, /31 uses both addresses (RFC 3021).
        if prefix == 32:
            first_host = last_host = str(network.network_address)
            gateway = str(network.network_address)
            usable = 1
        elif prefix == 31:
            first_host = str(network.network_address)
            last_host = str(network.broadcast_address)
            gateway = first_host
            usable = 2
        else:
            first_host = str(network.network_address + 1)
            last_host = str(network.broadcast_address - 1)
            gateway = first_host
            usable = network.num_addresses - 2

        if usable < request.hosts:
            # Should be impossible; guards against a future sizing regression.
            raise AddressSpaceExhaustedError(
                f"internal sizing error: /{prefix} provides {usable} hosts but "
                f"{request.hosts} were requested for {request.name}"
            )

        allocated.append(
            Subnet(
                name=request.name,
                requested_hosts=request.hosts,
                cidr=str(network),
                network=str(network.network_address),
                netmask=str(network.netmask),
                wildcard=str(network.hostmask),
                broadcast=str(network.broadcast_address),
                first_host=first_host,
                last_host=last_host,
                gateway=gateway,
                usable_hosts=usable,
                point_to_point=request.point_to_point,
            )
        )

        cursor = block_end_exclusive
        allocated_addresses += block_size

    _assert_no_overlap(allocated)

    requested_hosts = sum(request.hosts for request in requests)
    usable_hosts = sum(subnet.usable_hosts for subnet in allocated)
    utilization = Utilization(
        root_prefix=str(root),
        root_addresses=root.num_addresses,
        allocated_addresses=allocated_addresses,
        address_pct=round(allocated_addresses / root.num_addresses * 100, 2),
        requested_hosts=requested_hosts,
        usable_hosts=usable_hosts,
        host_pct=round(requested_hosts / usable_hosts * 100, 2) if usable_hosts else 100.0,
    )

    return VLSMAllocation(subnets=allocated, utilization=utilization)
