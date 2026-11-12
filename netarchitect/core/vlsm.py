"""Bitwise VLSM allocator.

Algorithm
---------
1. Parse the root prefix into an integer network and prefix length.
2. Sort requests by host count, largest first.  Ties keep their input order.
3. For each request compute the smallest power-of-two block that covers the
   need (``hosts + 2`` for a LAN, 4 for a /30, 2 for a /31).
4. Align the cursor upward with ``(cursor + size - 1) AND NOT (size - 1)``.
5. Stop with :class:`AddressSpaceExhaustedError` instead of wrapping past
   ``255.255.255.255`` or past the end of the root.
6. Re-check the finished plan for overlaps with an independent range scan.

Point-to-point behaviour follows RFC 3021 for /31 (both addresses usable, no
broadcast).  A /32 is a single host.  The gateway is the first usable address
for LAN blocks; the config generator uses the second and third addresses for
HSRP on a resilient core.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from netarchitect.core.errors import AddressSpaceExhaustedError, OverlapError
from netarchitect.core.ipv4 import (
    MAX_IPV4,
    block_size,
    broadcast_for,
    format_cidr,
    format_ipv4,
    network_of,
    parse_cidr,
    prefix_mask,
    wildcard_mask,
)
from netarchitect.core.spec import SubnetRequest


@dataclass(frozen=True)
class SubnetBlock:
    """One allocated subnet with every number the reports need."""

    name: str
    hosts: int
    prefix: int
    mode: str
    network_int: int = field(repr=False)
    broadcast_int: int = field(repr=False)
    vlan: int | None = None
    site: str | None = None
    between: tuple[str, str] | None = None
    poe: bool = False

    @property
    def size(self) -> int:
        return block_size(self.prefix)

    @property
    def network(self) -> str:
        return format_ipv4(self.network_int)

    @property
    def broadcast(self) -> str | None:
        return None if self.prefix >= 31 else format_ipv4(self.broadcast_int)

    @property
    def cidr(self) -> str:
        return format_cidr(self.network_int, self.prefix)

    @property
    def mask(self) -> str:
        return format_ipv4(prefix_mask(self.prefix))

    @property
    def wildcard(self) -> str:
        return format_ipv4(wildcard_mask(self.prefix))

    @property
    def first_usable_int(self) -> int:
        if self.prefix >= 31:
            return self.network_int
        return self.network_int + 1

    @property
    def last_usable_int(self) -> int:
        if self.prefix == 32:
            return self.network_int
        if self.prefix == 31:
            return self.network_int + 1
        return self.broadcast_int - 1

    @property
    def first_usable(self) -> str:
        return format_ipv4(self.first_usable_int)

    @property
    def last_usable(self) -> str:
        return format_ipv4(self.last_usable_int)

    @property
    def gateway(self) -> str:
        return self.first_usable

    @property
    def usable(self) -> int:
        if self.prefix == 32:
            return 1
        if self.prefix == 31:
            return 2
        return self.size - 2

    @property
    def utilization(self) -> float:
        if self.usable == 0:  # pragma: no cover - impossible by construction
            return 0.0
        return min(100.0, self.hosts / self.usable * 100.0)

    @property
    def point_to_point(self) -> bool:
        return self.mode in {"p2p30", "p2p31", "p2p32"}

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "hosts": self.hosts,
            "prefix": self.prefix,
            "mode": self.mode,
            "vlan": self.vlan,
            "site": self.site,
            "between": list(self.between) if self.between else None,
            "poe": self.poe,
            "network": self.network,
            "mask": self.mask,
            "wildcard": self.wildcard,
            "broadcast": self.broadcast,
            "first_usable": self.first_usable,
            "last_usable": self.last_usable,
            "gateway": self.gateway,
            "cidr": self.cidr,
            "usable": self.usable,
            "size": self.size,
            "utilization": round(self.utilization, 1),
        }


@dataclass(frozen=True)
class VLSMPlan:
    root: str
    blocks: tuple[SubnetBlock, ...]
    requested_total: int
    allocated_addresses: int
    usable_total: int
    root_size: int

    @property
    def utilization(self) -> float:
        if self.allocated_addresses == 0:
            return 0.0
        return self.requested_total / self.allocated_addresses * 100.0

    @property
    def usable_utilization(self) -> float:
        if self.usable_total == 0:
            return 0.0
        return self.requested_total / self.usable_total * 100.0

    @property
    def wasted(self) -> int:
        return max(0, self.root_size - self.allocated_addresses)

    def by_name(self, name: str) -> SubnetBlock | None:
        for block in self.blocks:
            if block.name.lower() == name.lower():
                return block
        return None

    def by_vlan(self, vlan: int) -> SubnetBlock | None:
        for block in self.blocks:
            if block.vlan == vlan:
                return block
        return None

    def by_site(self, site: str) -> list[SubnetBlock]:
        return [block for block in self.blocks if (block.site or "").lower() == site.lower()]

    def to_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            "blocks": [block.to_dict() for block in self.blocks],
            "requested_total": self.requested_total,
            "allocated_addresses": self.allocated_addresses,
            "usable_total": self.usable_total,
            "root_size": self.root_size,
            "utilization": round(self.utilization, 2),
            "usable_utilization": round(self.usable_utilization, 2),
            "wasted": self.wasted,
        }


def prefix_for_hosts(hosts: int, mode: str = "lan") -> int:
    """Smallest prefix that covers the request.

    * ``lan``   needs ``hosts + 2`` addresses (network and broadcast).
    * ``p2p30`` needs 4 addresses.
    * ``p2p31`` needs 2 addresses and follows RFC 3021.
    """
    if not isinstance(hosts, int) or isinstance(hosts, bool) or hosts < 1:
        raise ValueError("hosts must be a positive integer")
    if mode == "p2p30":
        need = 4
    elif mode == "p2p31":
        need = 2
    elif mode == "p2p32":
        need = 1
    elif mode == "lan":
        need = hosts + 2
    else:
        raise ValueError(f"unknown subnet mode: {mode}")
    bits = 0
    while (1 << bits) < need:
        bits += 1
    prefix = 32 - bits
    if prefix < 0:
        raise AddressSpaceExhaustedError(
            f"a request for {hosts} hosts needs more than the IPv4 address space"
        )
    return prefix


def _align_up(cursor: int, size: int) -> int:
    """Align an integer cursor to a power-of-two boundary."""
    return (cursor + size - 1) & ~(size - 1)


def allocate_vlsm(
    root_prefix: str,
    requests: Iterable[SubnetRequest],
) -> VLSMPlan:
    """Allocate every request inside ``root_prefix`` without overlap."""
    root_network, root_length = parse_cidr(root_prefix)
    root_size = block_size(root_length)
    root_end = root_network + root_size - 1

    items = list(requests)
    if not items:
        raise ValueError("at least one subnet request is required")

    ordered = sorted(
        enumerate(items),
        key=lambda pair: (-pair[1].hosts, pair[0]),
    )

    cursor = root_network
    blocks: list[SubnetBlock] = []
    for _, request in ordered:
        prefix = prefix_for_hosts(request.hosts, request.mode)
        size = block_size(prefix)
        aligned = _align_up(cursor, size)
        end = aligned + size - 1
        if aligned > MAX_IPV4 or end > MAX_IPV4 or end > root_end:
            raise AddressSpaceExhaustedError(
                f"address space {root_prefix} exhausted while allocating "
                f"{request.name!r} ({request.hosts} hosts, /{prefix}); "
                f"next aligned block would end at {end if end <= MAX_IPV4 else 'past 255.255.255.255'}"
            )
        blocks.append(
            SubnetBlock(
                name=request.name,
                hosts=request.hosts,
                prefix=prefix,
                mode=request.mode,
                network_int=aligned,
                broadcast_int=broadcast_for(aligned, prefix),
                vlan=request.vlan,
                site=request.site,
                between=request.between,
                poe=request.poe,
            )
        )
        cursor = end + 1

    _assert_no_overlap(blocks, root_network, root_end)

    requested_total = sum(block.hosts for block in blocks)
    allocated = sum(block.size for block in blocks)
    usable = sum(block.usable for block in blocks)
    return VLSMPlan(
        root=format_cidr(root_network, root_length),
        blocks=tuple(blocks),
        requested_total=requested_total,
        allocated_addresses=allocated,
        usable_total=usable,
        root_size=root_size,
    )


def _assert_no_overlap(blocks: list[SubnetBlock], root_network: int, root_end: int) -> None:
    """Independent safety net: scan the allocated ranges in address order."""
    ordered = sorted(blocks, key=lambda block: block.network_int)
    previous_end: int | None = None
    previous_name = ""
    for block in ordered:
        if block.network_int < root_network or block.broadcast_int > root_end:
            raise OverlapError(
                f"block {block.name!r} ({block.cidr}) leaves the root prefix"
            )
        if previous_end is not None and block.network_int <= previous_end:
            raise OverlapError(
                f"blocks {previous_name!r} and {block.name!r} overlap at "
                f"{format_ipv4(block.network_int)}"
            )
        previous_end = block.broadcast_int
        previous_name = block.name


def wildcard_for_prefix(prefix: int) -> str:
    return format_ipv4(wildcard_mask(prefix))


def mask_for_prefix(prefix: int) -> str:
    return format_ipv4(prefix_mask(prefix))


def network_address(address: int, prefix: int) -> int:
    return network_of(address, prefix)
