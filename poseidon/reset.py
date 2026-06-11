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
        """True when the crew conversation should start fresh.

        Phrase match fires even on the first turn; idle uses strict >
        (exactly idle_seconds keeps the thread); a turn exactly at the
        rollover instant counts as after it (last < rollover).
        Datetimes must be tz-aware (the daemon is aware throughout).
        """
        lowered = text.lower()
        if any(p in lowered for p in self.phrases):
            return True
        if last_turn_at is None:
            return False
        if last_turn_at.tzinfo is None or now.tzinfo is None:
            raise ValueError("should_reset requires tz-aware datetimes")
        if (now - last_turn_at).total_seconds() > self.idle_seconds:
            return True
        rollover = now.replace(hour=self.rollover_hour, minute=0,
                               second=0, microsecond=0)
        if now < rollover:
            rollover -= timedelta(days=1)
        return last_turn_at < rollover
