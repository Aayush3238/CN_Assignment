"""Bitwise IPv4 helpers.

No function here imports :mod:`ipaddress`.  Addresses are 32-bit integers and
prefixes are integers in ``0..32``; the conversion helpers only exist so the
engines can print dotted-quad strings.
"""

from __future__ import annotations

MAX_IPV4 = 0xFFFFFFFF


def parse_ipv4(text: object) -> int:
    """Parse a dotted-quad string into an unsigned 32-bit integer."""
    if not isinstance(text, str):
        raise ValueError("IPv4 address must be a string")
    parts = text.strip().split(".")
    if len(parts) != 4:
        raise ValueError(f"invalid IPv4 address: {text!r}")
    value = 0
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"invalid IPv4 address: {text!r}")
        octet = int(part)
        if octet < 0 or octet > 255:
            raise ValueError(f"invalid IPv4 address: {text!r}")
        value = (value << 8) | octet
    return value


def format_ipv4(value: int) -> str:
    """Render an unsigned 32-bit integer as a dotted-quad string."""
    if value < 0 or value > MAX_IPV4:
        raise ValueError(f"IPv4 value out of range: {value}")
    return ".".join(str((value >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def prefix_mask(prefix: int) -> int:
    """Return the 32-bit netmask for a prefix length."""
    if prefix < 0 or prefix > 32:
        raise ValueError(f"prefix must be 0..32, got {prefix}")
    if prefix == 0:
        return 0
    return (MAX_IPV4 << (32 - prefix)) & MAX_IPV4


def wildcard_mask(prefix: int) -> int:
    """Return the inverse mask used by OSPF and ACLs (RFC 4632)."""
    return (~prefix_mask(prefix)) & MAX_IPV4


def network_of(address: int, prefix: int) -> int:
    return address & prefix_mask(prefix)


def broadcast_of(address: int, prefix: int) -> int:
    return network_of(address, prefix) | wildcard_mask(prefix)


def parse_cidr(text: object) -> tuple[int, int]:
    """Parse ``a.b.c.d/p`` and return ``(network, prefix)``.

    Host bits are masked off so ``10.0.0.7/24`` becomes ``10.0.0.0/24``.
    """
    if not isinstance(text, str) or "/" not in text:
        raise ValueError(f"invalid CIDR prefix: {text!r}")
    address_text, _, prefix_text = text.partition("/")
    if not prefix_text.isdigit():
        raise ValueError(f"invalid CIDR prefix: {text!r}")
    prefix = int(prefix_text)
    if prefix < 0 or prefix > 32:
        raise ValueError(f"invalid CIDR prefix: {text!r}")
    address = parse_ipv4(address_text)
    return network_of(address, prefix), prefix


def format_cidr(network: int, prefix: int) -> str:
    return f"{format_ipv4(network)}/{prefix}"


def block_size(prefix: int) -> int:
    """Number of addresses in a block."""
    return 1 << (32 - prefix)


def broadcast_for(network: int, prefix: int) -> int:
    return network + block_size(prefix) - 1


def common_prefix(networks: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Shortest prefix that covers every ``(network, prefix)`` pair.

    Both the lowest and highest address in the set are used, so the result is
    independent of input order and cannot accidentally exclude a middle block.
    """
    if not networks:
        return None
    starts = [network for network, _ in networks]
    ends = [broadcast_for(network, prefix) for network, prefix in networks]
    first = min(starts)
    last = max(ends)
    differing = first ^ last
    common_bits = 32 - differing.bit_length()
    return network_of(first, common_bits), common_bits
