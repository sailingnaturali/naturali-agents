"""poseidon/capability.py — declared capability store (ADR 0003 / capability-memory spec).

A dedicated Mnemosyne data-dir (isolated from the crew store) holding one fact per
capability_map.json row. Seeding wipes and rebuilds from the JSON source of truth, so it
is trivially idempotent. Recall is engine-controlled semantic search used by the
fallback-on-stray path in engine.py. float32 vectors for semantic recall quality.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mnemosyne.core.memory import Mnemosyne

_MAP = Path(__file__).with_name("capability_map.json")

# Static tuning knobs — set once at import, never vary per-call.
os.environ.setdefault("MNEMOSYNE_VEC_TYPE", "float32")
os.environ.setdefault("MNEMOSYNE_LLM_ENABLED", "false")  # recall/seed never need an LLM


def _data_dir() -> Path:
    return Path(os.environ.get(
        "CAPABILITY_DATA_DIR",
        os.path.expanduser("~/.naturali/mnemosyne/capability")))


def _store() -> "Mnemosyne":
    # Mnemosyne uses thread-local SQLite connections internally: the stored
    # self.conn / self.beam.conn are thread-local handles that become invalid
    # when the object is used from a different thread (beam.recall raises
    # sqlite3.InterfaceError: bad parameter or other API misuse).  The daemon
    # calls recall_capabilities() via asyncio.to_thread(), so worker threads
    # differ from the thread that would have created a cached instance.
    # Per-call instantiation is the correct approach here — each call gets its
    # own thread-local connection, matching the thread-local architecture inside
    # Mnemosyne/BeamMemory.  The latency cost (model already loaded, only the
    # Python object and DB connection are re-created) is acceptable on the
    # infrequent fallback-on-stray path.
    os.environ["MNEMOSYNE_DATA_DIR"] = str(_data_dir())
    from mnemosyne.core.memory import Mnemosyne
    return Mnemosyne()


def seed_capabilities() -> int:
    """Wipe the capability store and rebuild it from capability_map.json. Returns fact count."""
    d = _data_dir()
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)
    mem = _store()
    rows = json.loads(_MAP.read_text(encoding="utf-8"))
    for row in rows:
        mem.remember(row["text"], source="capability_map",
                     metadata={"agent": row["agent"], "domain": row["domain"]})
    return len(rows)


def fact_count() -> int:
    """Return the total number of facts stored in the capability store."""
    mem = _store()
    return int(mem.get_stats().get("total_memories", 0))


def recall_capabilities(query: str, top_k: int = 5) -> list[str]:
    """Return capability fact texts semantically matching `query` (engine-controlled)."""
    if not query or not query.strip():
        return []
    mem = _store()
    results = mem.recall(query, top_k=top_k)
    out = []
    for r in results:
        content = r.get("content")
        if content:
            out.append(content)
    return out
