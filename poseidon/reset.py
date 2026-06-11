"""poseidon/reset.py — crew-conversation reset policy (spec §3)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class ResetPolicy:
    idle_seconds: float = 1800.0
    rollover_hour: int = 6
    phrases: tuple[str, ...] = ("new topic", "start fresh")

    def should_reset(self, last_turn_at: datetime | None,
                     now: datetime, text: str) -> bool:
        lowered = text.lower()
        if any(p in lowered for p in self.phrases):
            return True
        if last_turn_at is None:
            return False
        if (now - last_turn_at).total_seconds() > self.idle_seconds:
            return True
        rollover = now.replace(hour=self.rollover_hour, minute=0,
                               second=0, microsecond=0)
        if now < rollover:
            rollover -= timedelta(days=1)
        return last_turn_at < rollover
