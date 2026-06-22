import concurrent.futures
import os
from pathlib import Path

import pytest

from poseidon import capability


@pytest.fixture
def cap_dir(tmp_path, monkeypatch):
    d = tmp_path / "capability"
    monkeypatch.setenv("CAPABILITY_DATA_DIR", str(d))
    return d


def test_seed_is_idempotent(cap_dir):
    n1 = capability.seed_capabilities()
    n2 = capability.seed_capabilities()
    assert n1 == n2 == capability.fact_count()
    assert n1 >= 12  # one per capability_map.json row


def test_recall_matches_off_path_phrasing(cap_dir):
    # Probe genuine semantic bridging: no query word overlaps with the anchorages fact.
    # top_k=6 is large enough that the anchorages fact is reliably included even if
    # weather-domain facts rank higher at smaller k.
    capability.seed_capabilities()
    facts = capability.recall_capabilities("assessing shelter from swell and wind", top_k=6)
    assert facts, "recall returned no capability facts"
    joined = " ".join(facts).lower()
    assert "anchor" in joined, f"expected an anchor-domain fact in top-6 results; got: {facts}"


def test_recall_discriminates_by_domain(cap_dir):
    # Recall is relevance-filtered, not plain top-k truncation: a domain-specific
    # query surfaces that domain's facts and drops unrelated ones even at a large
    # top_k. This domain discrimination is precisely what makes capability recall
    # useful for routing.
    capability.seed_capabilities()
    facts = capability.recall_capabilities("battery charge and electrical systems", top_k=12)
    assert facts, "recall returned no capability facts"
    assert any("engineer" in f.lower() for f in facts), f"expected engineer facts: {facts}"
    assert len(facts) < 12, f"recall should filter by relevance, not return all: {facts}"


def test_recall_empty_on_unrelated(cap_dir):
    capability.seed_capabilities()
    facts = capability.recall_capabilities("", top_k=3)
    assert facts == []


def test_recall_is_thread_safe(cap_dir):
    # The daemon calls recall_capabilities() via asyncio.to_thread(), so worker
    # threads differ from the calling thread.  Per-call instantiation of Mnemosyne
    # is required because Mnemosyne stores thread-local SQLite connections at
    # construction time; a cached instance raises sqlite3.InterfaceError when
    # accessed from a different thread.  This test asserts that two concurrent
    # worker-thread calls both return facts without raising.
    capability.seed_capabilities()

    def worker():
        return capability.recall_capabilities("anchorage safety at night", top_k=3)

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(worker) for _ in range(2)]
        results = [f.result() for f in futs]

    assert all(len(r) > 0 for r in results), (
        f"expected non-empty results from both threads; got: {results}"
    )
