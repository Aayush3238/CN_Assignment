"""Layer-1 medium and transceiver selection with optical budgeting.

Boundaries are exclusive at the top of each band except where the
specification states otherwise:

===============  ==========================================  ==================
Distance         Choice                                      Standard
===============  ==========================================  ==================
<= 100 m         Cat6a copper, 10GBASE-T                     IEEE 802.3an
101 - 400 m      OM4 multimode, 10GBASE-SR, 850 nm           IEEE 802.3ae
> 400 m          OS2 single-mode, 10GBASE-LR (<= 10 km)      IEEE 802.3ae
> 10 km          OS2 single-mode, 10GBASE-ER (<= 40 km)      IEEE 802.3ae
> 40 km          ER with an amplification/DWDM warning       IEEE 802.3ae
===============  ==========================================  ==================

Copper requested past 100 m is a hard boundary error, never a clamp.
Optical loss is ``0.35 dB/km + 0.5 dB per connector + 0.1 dB per splice +
3.0 dB design margin``.  A span can be inside the transceiver's catalogue
reach and still warn, which is intentional: 40 km at 0.35 dB/km already spends
14 dB before connectors, splices, and margin.
"""

from __future__ import annotations

from dataclasses import dataclass

from netarchitect.core.errors import PhysicalDistanceViolationError
from netarchitect.core.spec import Link

COPPER_MAX_M = 100.0
MMF_MAX_M = 400.0
LR_MAX_M = 10_000.0
ER_MAX_M = 40_000.0

ATTENUATION_DB_PER_KM = 0.35
CONNECTOR_LOSS_DB = 0.5
SPLICE_LOSS_DB = 0.1
DESIGN_MARGIN_DB = 3.0

# IEEE 802.3ae minimum budgets.
LR_BUDGET_DB = 6.2  # -8.2 dBm transmit floor, -14.4 dBm receive sensitivity
ER_BUDGET_DB = 11.1  # -4.7 dBm transmit floor, -15.8 dBm receive sensitivity

_TOLERANCE = 1e-9


def format_distance(distance_m: float) -> str:
    """Human-readable distance; never scientific notation."""
    if distance_m >= 1000:
        kilometres = distance_m / 1000.0
        return f"{kilometres:.1f}".rstrip("0").rstrip(".") + " km"
    return f"{distance_m:.2f}".rstrip("0").rstrip(".") + " m"


@dataclass(frozen=True)
class MediaChoice:
    link: str
    distance_m: float
    kind: str
    medium: str
    standard: str
    transceiver: str
    wavelength_nm: int | None
    reach_m: float | None
    budget_db: float | None
    loss_db: float | None
    severity: str
    reason: str
    evidence: dict[str, object]

    @property
    def distance_label(self) -> str:
        return format_distance(self.distance_m)

    def to_dict(self) -> dict[str, object]:
        return {
            "link": self.link,
            "distance_m": self.distance_m,
            "distance_label": self.distance_label,
            "kind": self.kind,
            "medium": self.medium,
            "standard": self.standard,
            "transceiver": self.transceiver,
            "wavelength_nm": self.wavelength_nm,
            "reach_m": self.reach_m,
            "budget_db": self.budget_db,
            "loss_db": self.loss_db,
            "severity": self.severity,
            "reason": self.reason,
            "evidence": self.evidence,
        }


def optical_loss(distance_m: float, connectors: int, splices: int) -> float:
    """Simplified worst-case optical loss in dB."""
    return (
        (distance_m / 1000.0) * ATTENUATION_DB_PER_KM
        + connectors * CONNECTOR_LOSS_DB
        + splices * SPLICE_LOSS_DB
        + DESIGN_MARGIN_DB
    )


def select_media(link: Link) -> MediaChoice:
    """Apply the Layer-1 decision table to one link."""
    distance = link.distance_m
    if distance <= 0:
        raise PhysicalDistanceViolationError(
            f"link {link.name!r} has distance {distance:g} m; a physical run must be positive"
        )

    if distance <= COPPER_MAX_M + _TOLERANCE:
        if link.media == "copper":
            return _copper(link)
        if link.media == "fiber":
            return _multimode(link, requested=True)
        return _copper(link)

    if link.media == "copper":
        raise PhysicalDistanceViolationError(
            f"Cat6a copper (10GBASE-T) cannot carry link {link.name!r} at "
            f"{format_distance(distance)}: the IEEE 802.3an channel limit is 100 m. "
            "Signal attenuation beyond 100 m exceeds the 10GBASE-T link budget; "
            "use OM4 multimode to 400 m or OS2 single-mode beyond that."
        )

    if distance <= MMF_MAX_M + _TOLERANCE:
        return _multimode(link, requested=link.media == "fiber")

    return _single_mode(link)


def _copper(link: Link) -> MediaChoice:
    distance = link.distance_m
    reason = (
        f"Selected Cat6a copper with a 10GBASE-T transceiver because the "
        f"{link.kind} run ({format_distance(distance)}) is within the 100 m "
        "10GBASE-T channel limit (IEEE 802.3an). Category 6a supports 10 Gb/s "
        "over 100 m and is the lowest-cost medium at this distance."
    )
    return MediaChoice(
        link=link.name,
        distance_m=distance,
        kind=link.kind,
        medium="Cat6a copper",
        standard="IEEE 802.3an (10GBASE-T)",
        transceiver="10GBASE-T",
        wavelength_nm=None,
        reach_m=COPPER_MAX_M,
        budget_db=None,
        loss_db=None,
        severity="info",
        reason=reason,
        evidence={
            "limit_m": COPPER_MAX_M,
            "distance_m": distance,
            "headroom_m": round(COPPER_MAX_M - distance, 2),
        },
    )


def _multimode(link: Link, *, requested: bool) -> MediaChoice:
    distance = link.distance_m
    prefix = "Fiber was requested for" if requested else "Selected OM4 multimode fiber because"
    reason = (
        f"{prefix} the {link.kind} run ({format_distance(distance)}): it exceeds "
        "the 100 m Cat6a limit and stays inside the 400 m reach of 10GBASE-SR at "
        "850 nm (IEEE 802.3ae). Modal dispersion limits multimode reach, so the "
        "design stays within the 400 m OM4 catalogue distance."
    )
    return MediaChoice(
        link=link.name,
        distance_m=distance,
        kind=link.kind,
        medium="OM4 multimode fiber",
        standard="IEEE 802.3ae (10GBASE-SR)",
        transceiver="10GBASE-SR",
        wavelength_nm=850,
        reach_m=MMF_MAX_M,
        budget_db=None,
        loss_db=None,
        severity="info",
        reason=reason,
        evidence={
            "copper_limit_m": COPPER_MAX_M,
            "mmf_limit_m": MMF_MAX_M,
            "distance_m": distance,
            "headroom_m": round(MMF_MAX_M - distance, 2),
        },
    )


def _single_mode(link: Link) -> MediaChoice:
    distance = link.distance_m
    connectors = link.connectors
    splices = link.splices
    loss = optical_loss(distance, connectors, splices)

    if distance <= LR_MAX_M + _TOLERANCE:
        transceiver = "10GBASE-LR"
        wavelength = 1310
        budget = LR_BUDGET_DB
        reach = LR_MAX_M
    else:
        transceiver = "10GBASE-ER"
        wavelength = 1550
        budget = ER_BUDGET_DB
        reach = ER_MAX_M

    severity = "info"
    issues: list[str] = []
    if distance > ER_MAX_M + _TOLERANCE:
        severity = "warning"
        issues.append(
            f"the span exceeds the 40 km 10GBASE-ER catalogue reach, so it needs "
            "an amplifier or DWDM"
        )
    if loss > budget + _TOLERANCE:
        severity = "warning"
        issues.append(
            f"estimated loss {loss:.2f} dB exceeds the {budget:.1f} dB "
            f"{transceiver} budget"
        )

    reason = (
        f"Selected OS2 single-mode fiber with {transceiver} because the "
        f"{link.kind} run ({format_distance(distance)}) exceeds the 400 m "
        "attenuation limit of OM4 multimode fiber. OS2 has a 9 µm core and "
        f"carries {transceiver} at {wavelength} nm (IEEE 802.3ae). "
        f"Optical budget: {distance / 1000.0:.2f} km x {ATTENUATION_DB_PER_KM:g} dB/km "
        f"+ {connectors} connector(s) x {CONNECTOR_LOSS_DB:g} dB "
        f"+ {splices} splice(s) x {SPLICE_LOSS_DB:g} dB "
        f"+ {DESIGN_MARGIN_DB:g} dB margin = {loss:.2f} dB against a "
        f"{budget:.1f} dB budget."
    )
    if issues:
        reason += " Warning: " + "; ".join(issues) + "."

    return MediaChoice(
        link=link.name,
        distance_m=distance,
        kind=link.kind,
        medium="OS2 single-mode fiber",
        standard=f"IEEE 802.3ae ({transceiver})",
        transceiver=transceiver,
        wavelength_nm=wavelength,
        reach_m=reach,
        budget_db=budget,
        loss_db=round(loss, 2),
        severity=severity,
        reason=reason,
        evidence={
            "mmf_limit_m": MMF_MAX_M,
            "distance_m": distance,
            "reach_m": reach,
            "wavelength_nm": wavelength,
            "attenuation_db_per_km": ATTENUATION_DB_PER_KM,
            "connectors": connectors,
            "splices": splices,
            "margin_db": DESIGN_MARGIN_DB,
            "loss_db": round(loss, 2),
            "budget_db": budget,
            "headroom_db": round(budget - loss, 2),
        },
    )
