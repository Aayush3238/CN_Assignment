from __future__ import annotations

import ipaddress
import random

import pytest

from netarchitect.core.errors import AddressSpaceExhaustedError, OverlapError
from netarchitect.core.ipv4 import format_ipv4, parse_ipv4, wildcard_mask
from netarchitect.core.spec import SubnetRequest
from netarchitect.core.vlsm import allocate_vlsm, prefix_for_hosts, wildcard_for_prefix


def request(name, hosts, mode="lan"):
    return SubnetRequest(name=name, hosts=hosts, mode=mode)


def test_requests_sorted_descending_and_allocated_first():
    plan = allocate_vlsm(
        "10.0.0.0/16",
        [request("small", 50), request("large", 500), request("medium", 100)],
    )
    assert [block.name for block in plan.blocks] == ["large", "medium", "small"]
    assert plan.blocks[0].prefix == 23  # 500 + 2 -> 512
    assert plan.blocks[1].prefix == 25  # 100 + 2 -> 128
    assert plan.blocks[2].prefix == 26  # 50 + 2 -> 64


def test_no_overlap_and_correct_alignment():
    plan = allocate_vlsm(
        "10.0.0.0/24",
        [request("a", 100), request("b", 50), request("c", 20)],
    )
    ranges = [
        (parse_ipv4(block.network), parse_ipv4(block.broadcast)) for block in plan.blocks
    ]
    for index, (start, _end) in enumerate(ranges):
        assert start % block_size(plan.blocks[index].prefix) == 0
    for first, second in zip(ranges, ranges[1:]):
        assert second[0] > first[1]


def block_size(prefix):
    return 1 << (32 - prefix)


def test_exhaustion_does_not_wrap():
    with pytest.raises(AddressSpaceExhaustedError):
        allocate_vlsm("10.0.0.0/24", [request("big", 200), request("more", 100)])


def test_exact_fit():
    plan = allocate_vlsm("10.0.0.0/25", [request("only", 126)])
    assert plan.blocks[0].cidr == "10.0.0.0/25"
    assert plan.blocks[0].usable == 126


@pytest.mark.parametrize(
    ("mode", "hosts", "prefix"),
    [("lan", 2, 30), ("lan", 1, 30), ("p2p30", 2, 30), ("p2p31", 2, 31)],
)
def test_prefix_for_hosts(mode, hosts, prefix):
    assert prefix_for_hosts(hosts, mode) == prefix


def test_rfc3021_slash31_has_no_broadcast():
    plan = allocate_vlsm("10.0.0.0/30", [request("p2p", 2, mode="p2p31")])
    block = plan.blocks[0]
    assert block.prefix == 31
    assert block.broadcast is None
    assert block.usable == 2
    assert block.first_usable == "10.0.0.0"
    assert block.last_usable == "10.0.0.1"


def test_slash32_single_host():
    plan = allocate_vlsm("10.0.0.0/30", [request("loopback", 1, mode="p2p32")])
    block = plan.blocks[0]
    assert block.prefix == 32
    assert block.broadcast is None
    assert block.usable == 1
    assert block.first_usable == block.last_usable == block.gateway == "10.0.0.0"


def test_gateway_is_first_usable():
    plan = allocate_vlsm("10.0.0.0/24", [request("lan", 100)])
    block = plan.blocks[0]
    assert block.gateway == block.first_usable == "10.0.0.1"
    assert block.broadcast == "10.0.0.127"


def test_wildcard_is_inverse_mask():
    plan = allocate_vlsm("10.0.0.0/24", [request("lan", 100)])
    block = plan.blocks[0]
    assert block.wildcard == "0.0.0.127"
    assert block.mask == "255.255.255.128"


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
def test_wildcard_for_prefix(prefix, wildcard):
    assert wildcard_for_prefix(prefix) == wildcard


def test_utilization_math():
    plan = allocate_vlsm("10.0.0.0/24", [request("a", 100), request("b", 50)])
    assert plan.allocated_addresses == 192
    assert plan.requested_total == 150
    assert plan.utilization == pytest.approx(150 / 192 * 100)
    assert plan.usable_utilization == pytest.approx(150 / (126 + 62) * 100)


def test_thousand_random_plans_do_not_overlap_and_stay_in_root():
    rng = random.Random(20261110)
    root = ipaddress.ip_network("10.0.0.0/16")
    for _ in range(1000):
        count = rng.randint(1, 8)
        counts = [rng.randint(1, 400) for _ in range(count)]
        requests = [request(f"s{index}", value) for index, value in enumerate(counts)]
        plan = allocate_vlsm(str(root), requests)
        networks = [ipaddress.ip_network(block.cidr) for block in plan.blocks]
        for network in networks:
            assert network.subnet_of(root)
        for index, first in enumerate(networks):
            for second in networks[index + 1 :]:
                assert not first.overlaps(second)
