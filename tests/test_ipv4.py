from __future__ import annotations

import pytest

from netarchitect.core.ipv4 import (
    common_prefix,
    format_cidr,
    format_ipv4,
    parse_cidr,
    parse_ipv4,
    prefix_mask,
    wildcard_mask,
)


@pytest.mark.parametrize(
    ("address", "value"),
    [
        ("0.0.0.0", 0),
        ("255.255.255.255", 0xFFFFFFFF),
        ("10.0.0.1", 0x0A000001),
        ("192.168.1.1", 0xC0A80101),
    ],
)
def test_parse_format_round_trip(address, value):
    assert parse_ipv4(address) == value
    assert format_ipv4(value) == address


@pytest.mark.parametrize("bad", ["10.0.0", "10.0.0.256", "10.0.0.x", "", "1.2.3.4.5"])
def test_bad_ipv4_rejected(bad):
    with pytest.raises(ValueError):
        parse_ipv4(bad)


@pytest.mark.parametrize(
    ("prefix", "wildcard"),
    [
        (0, "255.255.255.255"),
        (8, "0.255.255.255"),
        (24, "0.0.0.255"),
        (30, "0.0.0.3"),
        (31, "0.0.0.1"),
        (32, "0.0.0.0"),
    ],
)
def test_wildcard_masks(prefix, wildcard):
    assert format_ipv4(wildcard_mask(prefix)) == wildcard
    assert format_ipv4(prefix_mask(prefix)) == format_ipv4(~wildcard_mask(prefix) & 0xFFFFFFFF)


def test_cidr_masks_host_bits():
    network, prefix = parse_cidr("10.0.0.7/24")
    assert prefix == 24
    assert format_cidr(network, prefix) == "10.0.0.0/24"


def test_common_prefix_covers_all_blocks():
    blocks = [parse_cidr("10.20.1.128/25"), parse_cidr("10.20.1.0/25")]
    network, prefix = common_prefix(blocks)
    assert format_cidr(network, prefix) == "10.20.1.0/24"
