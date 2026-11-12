from __future__ import annotations

import pytest

from netarchitect.core.errors import PhysicalDistanceViolationError
from netarchitect.core.media import (
    COPPER_MAX_M,
    ER_BUDGET_DB,
    LR_BUDGET_DB,
    format_distance,
    optical_loss,
    select_media,
)
from netarchitect.core.spec import Link


def link(distance, *, media="auto", kind="backbone", connectors=2, splices=0):
    return Link("test", distance, kind, media, connectors, splices)


@pytest.mark.parametrize(
    ("distance", "medium", "transceiver"),
    [
        (1, "Cat6a copper", "10GBASE-T"),
        (100, "Cat6a copper", "10GBASE-T"),
        (101, "OM4 multimode fiber", "10GBASE-SR"),
        (400, "OM4 multimode fiber", "10GBASE-SR"),
        (401, "OS2 single-mode fiber", "10GBASE-LR"),
        (10_000, "OS2 single-mode fiber", "10GBASE-LR"),
        (10_001, "OS2 single-mode fiber", "10GBASE-ER"),
        (40_000, "OS2 single-mode fiber", "10GBASE-ER"),
    ],
)
def test_media_boundaries(distance, medium, transceiver):
    choice = select_media(link(distance))
    assert choice.medium == medium
    assert choice.transceiver == transceiver


def test_copper_past_100m_raises_with_attenuation_warning():
    with pytest.raises(PhysicalDistanceViolationError, match="100 m"):
        select_media(link(101, media="copper"))


def test_fifty_km_warns_about_amplification():
    choice = select_media(link(50_000))
    assert choice.severity == "warning"
    assert "amplifier" in choice.reason or "DWDM" in choice.reason


def test_optical_loss_includes_connectors_splices_and_margin():
    # 10 km * 0.35 + 2 * 0.5 + 2 * 0.1 + 3.0 = 7.7
    assert optical_loss(10_000, 2, 2) == pytest.approx(7.7)


def test_er_budget_is_used_after_10km():
    choice = select_media(link(22_000))
    assert choice.budget_db == ER_BUDGET_DB
    assert choice.transceiver == "10GBASE-ER"
    assert "dB" in choice.reason


def test_lr_budget_named_in_reason():
    choice = select_media(link(5_000))
    assert choice.budget_db == LR_BUDGET_DB
    assert "6.2" in choice.reason


def test_distance_format_never_scientific():
    assert format_distance(90) == "90 m"
    assert format_distance(22_000) == "22 km"
    assert format_distance(5_000_000) == "5000 km"
    assert "e+" not in format_distance(5_000_000)
