"""VLSM sizing, allocation, overlap, and edge-case tests."""

import ipaddress

import pytest

from netarchitect.core.errors import AddressSpaceExhaustedError
from netarchitect.core.vlsm import (
    VLSMRequest,
    allocate_vlsm,
    prefix_for_hosts,
    wildcard_mask,
)


@pytest.mark.parametrize(
    ("hosts", "prefix"),
    [(1, 32), (2, 30), (3, 29), (20, 27), (100, 25), (400, 23), (500, 23)],
)
def test_prefix_for_hosts(hosts, prefix):
    assert prefix_for_hosts(hosts) == prefix


def test_point_to_point_uses_rfc3021():
    assert prefix_for_hosts(2, point_to_point=True) == 31


def test_allocation_is_descending_and_contiguous():
    allocation = allocate_vlsm(
        "10.0.0.0/24",
        [
            VLSMRequest("small", 20),
            VLSMRequest("large", 100),
            VLSMRequest("medium", 50),
        ],
    )
    by_name = {subnet.name: subnet for subnet in allocation.subnets}
    assert by_name["large"].cidr == "10.0.0.0/25"
    assert by_name["medium"].cidr == "10.0.0.128/26"
    assert by_name["small"].cidr == "10.0.0.192/27"
    assert allocation.utilization.address_pct == pytest.approx(87.5)


def test_allocated_subnets_never_overlap():
    allocation = allocate_vlsm(
        "10.0.0.0/22",
        [VLSMRequest(f"vlan-{index}", hosts=index * 7) for index in range(1, 12)],
    )
    ranges = []
    for subnet in allocation.subnets:
        network = ipaddress.ip_network(subnet.cidr)
        ranges.append((int(network.network_address), int(network.broadcast_address)))
    ranges.sort()
    for (_, end_a), (start_b, _) in zip(ranges, ranges[1:]):
        assert start_b > end_a


def test_address_space_exhaustion_raises():
    with pytest.raises(AddressSpaceExhaustedError):
        allocate_vlsm(
            "10.0.0.0/24",
            [VLSMRequest("first", 200), VLSMRequest("second", 100)],
        )


def test_single_host_gets_slash_32():
    allocation = allocate_vlsm("10.0.0.0/29", [VLSMRequest("loopback", 1)])
    subnet = allocation.subnets[0]
    assert subnet.cidr == "10.0.0.0/32"
    assert subnet.usable_hosts == 1
    assert subnet.gateway == "10.0.0.0"
    assert subnet.first_host == subnet.last_host == "10.0.0.0"


def test_point_to_point_gets_slash_31():
    allocation = allocate_vlsm(
        "10.0.0.0/30", [VLSMRequest("p2p", 2, point_to_point=True)]
    )
    subnet = allocation.subnets[0]
    assert subnet.cidr == "10.0.0.0/31"
    assert subnet.usable_hosts == 2
    assert subnet.gateway == "10.0.0.0"
    assert subnet.broadcast == "10.0.0.1"


@pytest.mark.parametrize(
    ("prefix", "wildcard"),
    [(24, "0.0.0.255"), (23, "0.0.1.255"), (30, "0.0.0.3"), (32, "0.0.0.0")],
)
def test_wildcard_masks(prefix, wildcard):
    assert wildcard_mask(prefix) == wildcard


def test_duplicate_names_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        allocate_vlsm(
            "10.0.0.0/24",
            [VLSMRequest("same", 10), VLSMRequest("same", 10)],
        )


def test_root_prefix_too_small_is_rejected():
    with pytest.raises(ValueError):
        allocate_vlsm("10.0.0.0/31", [VLSMRequest("host", 1)])
