"""Market data service: watchlist management, snapshot cache, 15s refresh loop."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from .gateway_gtimg import TencentGateway, bar_to_dict, tick_to_dict

log = logging.getLogger("market")

WATCHLIST_PATH = Path(__file__).resolve().parent.parent / "watchlist.json"
REFRESH_SECONDS = 15


class MarketData:
    def __init__(self) -> None:
        self.gateway = TencentGateway()
        self._spot: dict[str, dict] = {}   # symbol -> quote dict
        self._watchlist: list[dict] = json.loads(WATCHLIST_PATH.read_text())
        self.stale: bool = False
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._subscribers: set[asyncio.Queue] = set()

    # -- watchlist -----------------------------------------------------------
    @property
    def watchlist(self) -> list[dict]:
        return list(self._watchlist)

    def _save(self) -> None:
        WATCHLIST_PATH.write_text(json.dumps(self._watchlist, ensure_ascii=False, indent=2))

    def add_symbol(self, symbol: str, kind: str = "stock") -> None:
        if not any(w["symbol"] == symbol for w in self._watchlist):
            self._watchlist.append({"symbol": symbol, "kind": kind})
            self._save()

    def remove_symbol(self, symbol: str) -> None:
        self._watchlist = [w for w in self._watchlist if w["symbol"] != symbol]
        self._save()

    # -- refresh loop --------------------------------------------------------
    async def start(self) -> None:
        await self.refresh_once()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            await self.refresh_once()

    async def refresh_once(self) -> None:
        try:
            items = [(w["symbol"], w["kind"]) for w in self._watchlist]
            ticks = await asyncio.to_thread(self.gateway.query_quotes, items)
            async with self._lock:
                self._spot = {t.symbol: tick_to_dict(t) for t in ticks}
            self.stale = False
        except Exception:
            log.exception("quote refresh failed; keeping previous snapshot")
            self.stale = True
        await self._broadcast()

    # -- queries -------------------------------------------------------------
    async def get_watchlist_quotes(self) -> list[dict]:
        async with self._lock:
            out = []
            for w in self._watchlist:
                q = self._spot.get(w["symbol"], {})
                out.append({**w, **q, "stale": self.stale})
            return out

    async def get_quote(self, symbol: str) -> dict | None:
        async with self._lock:
            q = self._spot.get(symbol)
            return {**q, "stale": self.stale} if q else None

    async def get_kline(self, symbol: str, period: str, count: int) -> list[dict]:
        kind = next((w["kind"] for w in self._watchlist if w["symbol"] == symbol), "stock")
        bars = await asyncio.to_thread(self.gateway.query_bars, symbol, period, count, kind)
        return [bar_to_dict(b) for b in bars]

    # -- pub/sub for websocket ----------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=1)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _broadcast(self) -> None:
        payload = await self.get_watchlist_quotes()
        for q in list(self._subscribers):
            if q.full():
                q.get_nowait()  # drop the older frame; clients always want latest
            q.put_nowait(payload)
