"""In-process lock that serializes balance/stock mutations.

Correctness never depends on it (all money/stock updates are conditional UPDATEs
that check rowcount), but it avoids needless write contention on SQLite.
"""
from __future__ import annotations

import asyncio
import weakref

_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


def money_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock
