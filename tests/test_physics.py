"""L1 media boundary and optical budget tests."""

import pytest

from netarchitect.core.errors import (
    OpticalBudgetViolationError,
    PhysicalDistanceViolationError,
)
from netarchitect.core.models import LinkSpec
from netarchitect.core.physics import select_media


def _link(distance: float, **overrides) -> LinkSpec:
    data = {"name": "test link", "distance_m": distance, "category": "backbone"}
    data.update(overrides)
    return LinkSpec(**data)


@pytest.mark.parametrize(
    ("distance", "media", "transceiver"),
    [
        (99, "Cat6a copper", "10GBASE-T"),
        (100, "Cat6a copper", "10GBASE-T"),
        (101, "OM4 multimode fiber", "10GBASE-SR"),
        (400, "OM4 multimode fiber", "10GBASE-SR"),
        (401, "OS2 single-mode fiber", "10GBASE-LR"),
        (5000, "OS2 single-mode fiber", "10GBASE-LR"),
        (22000, "OS2 single-mode fiber", "10GBASE-ER"),
    ],
)
def test_distance_boundaries(distance, media, transceiver):
    recommendation = select_media(_link(distance))
    assert recommendation.media == media
    assert recommendation.transceiver == transceiver
    assert recommendation.rationale


def test_copper_request_beyond_100m_raises():
    with pytest.raises(PhysicalDistanceViolationError, match="100 m"):
        select_media(_link(101, requested_media="copper"))


def test_copper_request_at_limit_is_allowed():
    recommendation = select_media(_link(100, requested_media="copper"))
    assert recommendation.media == "Cat6a copper"
    assert recommendation.rule_id == "L1-EXPLICIT-01"


def test_multimode_request_beyond_400m_raises():
    with pytest.raises(PhysicalDistanceViolationError, match="400 m"):
        select_media(_link(401, requested_media="mmf"))


def test_single_mode_request_beyond_er_reach_raises():
    with pytest.raises(OpticalBudgetViolationError, match="40 km"):
        select_media(_link(45_000))


def test_single_mode_optical_budget_is_checked():
    # 15 km and 35 km both fit the ER budget; the rationale must show the math.
    for distance in (15_000, 35_000):
        recommendation = select_media(_link(distance))
        assert recommendation.transceiver == "10GBASE-ER"
        assert "dB budget" in recommendation.rationale


def test_internet_wan_selects_carrier_service():
    recommendation = select_media(
        _link(5_000_000, category="wan", service="internet")
    )
    assert recommendation.rule_id == "L1-WAN-CARRIER"
    assert "IPsec" in recommendation.media
    assert "Carrier" in recommendation.media


def test_dark_fiber_wan_uses_single_mode():
    recommendation = select_media(
        _link(22_000, category="wan", service="dark-fiber")
    )
    assert recommendation.media == "OS2 single-mode fiber"
    assert recommendation.transceiver == "10GBASE-ER"
