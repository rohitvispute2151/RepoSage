import asyncio
import uuid
from datetime import datetime, timezone

from reposage.workers.events import EventRecorder


async def _run(emits, start_seq=0, fail_on=None):
    stored = []

    async def write(task_id, seq, etype, payload):
        if etype == fail_on:
            raise RuntimeError("db down")
        stored.append((seq, etype, payload))

    async def last_seq(_):
        return start_seq

    rec = EventRecorder("t1", write=write, last_seq=last_seq)
    await rec.start()
    for etype, payload in emits:
        rec.sink("t1", etype, payload)
    await rec.close()
    return stored


def test_events_are_stored_in_order_with_monotonic_seq():
    out = asyncio.run(_run([("node_started", {"node": "plan"}), ("node_finished", {"node": "plan"}), ("completed", {"status": "completed"})]))
    assert [(s, t) for s, t, _ in out] == [(1, "node_started"), (2, "node_finished"), (3, "completed")]


def test_resumed_task_continues_the_sequence():
    out = asyncio.run(_run([("approval_requested", {})], start_seq=15))
    assert out[0][0] == 16


def test_close_flushes_everything_queued():
    out = asyncio.run(_run([("node_started", {"node": str(i)}) for i in range(200)]))
    assert len(out) == 200 and out[-1][0] == 200


def test_payload_is_made_json_safe():
    out = asyncio.run(_run([("x", {"id": uuid.UUID(int=1), "at": datetime(2026, 1, 1, tzinfo=timezone.utc)})]))
    assert isinstance(out[0][2]["id"], str) and isinstance(out[0][2]["at"], str)


def test_a_failed_write_is_dropped_without_stopping_the_stream():
    out = asyncio.run(_run([("a", {}), ("bad", {}), ("c", {})], fail_on="bad"))
    assert [t for _, t, _ in out] == ["a", "c"]
