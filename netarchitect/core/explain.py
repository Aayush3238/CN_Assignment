"""Explainability support.

Every rule the engine applies should leave an audit trail. The collector keeps
those records in evaluation order so the CLI/export shows *why* each choice was
made, not just the final answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from netarchitect.core.models import Rationale


@dataclass
class RationaleCollector:
    """Accumulates machine-readable justifications for one run."""

    entries: list[Rationale] = field(default_factory=list)

    def add(
        self,
        *,
        rule_id: str,
        domain: str,
        inputs: dict,
        condition: str,
        choice: str,
        rationale: str,
        standard: str = "",
    ) -> None:
        """Record one decision.

        ``inputs`` is copied into the model so later mutation of the engine's
        working dict cannot rewrite history.
        """
        self.entries.append(
            Rationale(
                rule_id=rule_id,
                domain=domain,
                inputs=dict(inputs),
                condition=condition,
                choice=choice,
                rationale=rationale,
                standard=standard,
            )
        )
