"""FastAPI entry: REST + WebSocket for the alpha-desk quant terminal."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import agent_bridge, experts
from .market import MarketData

logging.basicConfig(level=logging.INFO)

market = MarketData()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await market.start()
    yield
    await market.stop()


app = FastAPI(title="alpha-desk terminal", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- quotes ------------------------------------------------------------------
@app.get("/api/watchlist")
async def get_watchlist() -> list[dict]:
    return await market.get_watchlist_quotes()


class WatchlistItem(BaseModel):
    symbol: str
    kind: str = "stock"


@app.put("/api/watchlist")
async def put_watchlist(item: WatchlistItem) -> list[dict]:
    if not item.symbol.isdigit() or len(item.symbol) != 6:
        raise HTTPException(400, "symbol 必须是 6 位数字代码")
    market.add_symbol(item.symbol, item.kind)
    await market.refresh_once()
    return await market.get_watchlist_quotes()


@app.delete("/api/watchlist/{symbol}")
async def delete_watchlist(symbol: str) -> list[dict]:
    market.remove_symbol(symbol)
    return await market.get_watchlist_quotes()


@app.get("/api/quote/{symbol}")
async def get_quote(symbol: str) -> dict:
    q = await market.get_quote(symbol)
    if q is None:
        raise HTTPException(404, f"无 {symbol} 的快照,请先加入自选")
    return q


@app.get("/api/kline")
async def get_kline(symbol: str, period: str = "daily", count: int = 200) -> list[dict]:
    if period not in {"daily", "60", "30", "15", "5"}:
        raise HTTPException(400, "period 仅支持 daily/60/30/15/5")
    count = max(10, min(500, count))
    try:
        return await market.get_kline(symbol, period, count)
    except Exception as exc:
        raise HTTPException(502, f"K线数据获取失败: {exc}")


# -- agent chat ---------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    symbol: str | None = None
    symbol_name: str | None = None


@app.post("/api/chat")
async def post_chat(req: ChatRequest) -> dict:
    if not req.message.strip():
        raise HTTPException(400, "message 不能为空")
    try:
        return await agent_bridge.chat(req.message, req.symbol, req.symbol_name)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


# -- expert panel --------------------------------------------------------------
class ExpertsRequest(BaseModel):
    tickers: str  # 逗号分隔,如 "AAPL,MSFT,NVDA"


@app.post("/api/experts")
async def post_experts(req: ExpertsRequest) -> dict:
    tickers = [t for t in req.tickers.replace(" ", ",").split(",") if t.strip()]
    if not tickers:
        raise HTTPException(400, "tickers 不能为空")
    try:
        return await experts.run_experts(tickers)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc))


# -- websocket ----------------------------------------------------------------
@app.websocket("/ws/quotes")
async def ws_quotes(ws: WebSocket) -> None:
    await ws.accept()
    queue = market.subscribe()
    try:
        await ws.send_json(await market.get_watchlist_quotes())  # initial frame
        while True:
            payload = await queue.get()
            await ws.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        market.unsubscribe(queue)
