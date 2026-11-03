"""Layer-1 media selection and distance/budget physics.

Rules implemented from the assignment specification:
* <= 100 m access  -> Cat6a (10GBASE-T, IEEE 802.3an)
* 101-400 m backbone -> OM4 multimode (10GBASE-SR, 850 nm)
* > 400 m          -> OS2 single-mode (10GBASE-LR/ER)
* copper requested > 100 m -> PhysicalDistanceViolationError

For single-mode links we also compute a simplified optical power budget
(fiber attenuation + connector + splice losses) rather than blindly trusting
the datasheet reach.
"""

from __future__ import annotations

from netarchitect.core.errors import (
    OpticalBudgetViolationError,
    PhysicalDistanceViolationError,
)
from netarchitect.core.models import LinkSpec, MediaRecommendation

COPPER_MAX_M = 100.0
MMF_MAX_M = 400.0

# 10GBASE-LR: 1310 nm, ~10 km nominal reach, IEEE 802.3ae power budget ~6.2 dB.
LR_MAX_M = 10_000.0
LR_ATTENUATION_DB_PER_KM = 0.35
LR_BUDGET_DB = 6.2

# 10GBASE-ER: 1550 nm, ~40 km nominal reach, IEEE 802.3ae power budget ~10.5 dB.
ER_MAX_M = 40_000.0
ER_ATTENUATION_DB_PER_KM = 0.25
ER_BUDGET_DB = 10.5

# Passive plant allowances. Two patch-panel connectors (0.5 dB each) plus one
# splice per ~10 km is a conservative planning assumption.
CONNECTOR_LOSS_DB = 1.0
SPLICE_LOSS_DB = 0.1


def _distance_label(distance_m: float) -> str:
    """Format a distance for rationales (metres below 1 km, otherwise km)."""
    if distance_m >= 1000:
        return f"{distance_m / 1000:.1f} km"
    return f"{distance_m:.0f} m"


def _copper_recommendation(link: LinkSpec, explicit: bool) -> MediaRecommendation:
    distance = link.distance_m
    rationale = (
        f"Selected Cat6a (10GBASE-T) because the {_distance_label(distance)} run is "
        "within the 100 m limit defined by IEEE 802.3an; Cat6a sustains 10 Gbps "
        "at this distance without active optics."
    )
    if explicit:
        rationale += " Copper was explicitly requested and the distance constraint is satisfied."
    return MediaRecommendation(
        link=link.name,
        distance_m=distance,
        category=link.category,
        media="Cat6a copper",
        transceiver="10GBASE-T",
        standard="IEEE 802.3an",
        rationale=rationale,
        rule_id="L1-EXPLICIT-01" if explicit else "L1-DIST-01",
    )


def _mmf_recommendation(link: LinkSpec, explicit: bool) -> MediaRecommendation:
    distance = link.distance_m
    rationale = (
        f"Selected OM4 Multimode Fiber (10GBASE-SR) because the "
        f"{_distance_label(distance)} run exceeds the 100 m copper limit but remains "
        "inside the 400 m OM4 reach at 850 nm, where modal dispersion and "
        "attenuation stay within budget."
    )
    if explicit:
        rationale += " Multimode fiber was explicitly requested."
    return MediaRecommendation(
        link=link.name,
        distance_m=distance,
        category=link.category,
        media="OM4 multimode fiber",
        transceiver="10GBASE-SR",
        standard="IEEE 802.3ae (850 nm)",
        rationale=rationale,
        rule_id="L1-EXPLICIT-02" if explicit else "L1-DIST-02",
    )


def _smf_recommendation(link: LinkSpec, explicit: bool) -> MediaRecommendation:
    """Pick LR vs ER based on reach and verify a simple optical budget."""
    distance = link.distance_m
    distance_km = distance / 1000.0

    if distance <= LR_MAX_M:
        transceiver = "10GBASE-LR"
        wavelength = "1310 nm"
        attenuation = LR_ATTENUATION_DB_PER_KM
        budget = LR_BUDGET_DB
        reach = "10 km"
    elif distance <= ER_MAX_M:
        transceiver = "10GBASE-ER"
        wavelength = "1550 nm"
        attenuation = ER_ATTENUATION_DB_PER_KM
        budget = ER_BUDGET_DB
        reach = "40 km"
    else:
        raise OpticalBudgetViolationError(
            f"Link '{link.name}' is {_distance_label(distance)}, which exceeds the "
            f"40 km 10GBASE-ER reach. Use a carrier Ethernet/IPsec WAN service "
            "instead of a direct single-mode run."
        )

    # Conservative loss model: fiber attenuation + connectors + splices.
    splices = max(1, round(distance_km / 10))
    fiber_loss = distance_km * attenuation
    splice_loss = splices * SPLICE_LOSS_DB
    total_loss = fiber_loss + CONNECTOR_LOSS_DB + splice_loss

    if total_loss > budget:
        raise OpticalBudgetViolationError(
            f"Link '{link.name}' ({_distance_label(distance)}) needs "
            f"{total_loss:.1f} dB of optical loss but {transceiver} only provides "
            f"{budget:.1f} dB. Reduce the run or select a carrier service."
        )

    rationale = (
        f"Selected OS2 Single-Mode Fiber because link distance "
        f"({_distance_label(distance)}) exceeds the 400 m attenuation limit of OM4 "
        f"Multimode Fiber. Chose {transceiver} ({wavelength}) with a calculated "
        f"link loss of {total_loss:.1f} dB against a {budget:.1f} dB budget "
        f"({fiber_loss:.1f} dB fiber + {CONNECTOR_LOSS_DB:.1f} dB connectors + "
        f"{splice_loss:.1f} dB splices); nominal reach is {reach}."
    )
    if explicit:
        rationale += " Single-mode fiber was explicitly requested."
    return MediaRecommendation(
        link=link.name,
        distance_m=distance,
        category=link.category,
        media="OS2 single-mode fiber",
        transceiver=transceiver,
        standard=f"IEEE 802.3ae ({wavelength})",
        rationale=rationale,
        rule_id="L1-EXPLICIT-03" if explicit else "L1-DIST-03",
    )


def _carrier_wan_recommendation(link: LinkSpec) -> MediaRecommendation:
    """Internet-based WAN: buy a carrier handoff, protect it with IPsec.

    Direct single-mode fiber is not realistic across cities/continents, so the
    L1 decision is the carrier service and the L3 decision is IPsec encryption.
    """
    distance = link.distance_m
    return MediaRecommendation(
        link=link.name,
        distance_m=distance,
        category=link.category,
        media="ISP Carrier Ethernet + IPsec VPN",
        transceiver="N/A (service handoff)",
        standard="RFC 4301 (IPsec)",
        rationale=(
            f"Selected an ISP Carrier Ethernet handoff protected by IPsec because "
            f"the {_distance_label(distance)} multi-city path cannot be served by a "
            "direct single-mode run at acceptable cost. The carrier provides the L1 "
            "transport and the enterprise overlay provides confidentiality and "
            "route isolation across the public WAN."
        ),
        rule_id="L1-WAN-CARRIER",
    )


def select_media(link: LinkSpec) -> MediaRecommendation:
    """Apply the distance rules and return a justified media recommendation.

    Raises:
        PhysicalDistanceViolationError: for copper/multimode requests beyond
            their physical reach.
        OpticalBudgetViolationError: when a single-mode link exceeds LR/ER
            reach or its calculated power budget.
    """
    distance = link.distance_m
    requested = link.requested_media

    # Internet WANs are a service decision, not a cable-length decision.
    if link.category == "wan" and link.service == "internet":
        return _carrier_wan_recommendation(link)

    if requested == "copper":
        if distance > COPPER_MAX_M:
            raise PhysicalDistanceViolationError(
                f"Copper requested for '{link.name}' at {_distance_label(distance)}, "
                "but twisted-pair Ethernet is limited to 100 m. Signal attenuation "
                "and crosstalk make this run unreliable; use OM4 (<=400 m) or OS2 "
                "single-mode fiber instead."
            )
        return _copper_recommendation(link, explicit=True)

    if requested == "mmf":
        if distance > MMF_MAX_M:
            raise PhysicalDistanceViolationError(
                f"Multimode requested for '{link.name}' at {_distance_label(distance)}, "
                "but OM4 10GBASE-SR is limited to 400 m at 850 nm. Modal dispersion "
                "exceeds the link budget; select OS2 single-mode fiber."
            )
        return _mmf_recommendation(link, explicit=True)

    if requested == "smf":
        return _smf_recommendation(link, explicit=True)

    # Automatic selection by distance.
    if distance <= COPPER_MAX_M:
        return _copper_recommendation(link, explicit=False)
    if distance <= MMF_MAX_M:
        return _mmf_recommendation(link, explicit=False)
    return _smf_recommendation(link, explicit=False)
