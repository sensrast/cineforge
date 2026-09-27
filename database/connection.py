"""Single shared async SQLite connection with transaction-safe helpers."""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Any
import aiosqlite

class Database:
    def __init__(self, path: Path): self.path, self.conn, self.lock = path, None, asyncio.Lock()
    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.execute("PRAGMA foreign_keys=ON")
        await self.conn.execute("PRAGMA journal_mode=WAL")
    async def init_schema(self, schema: Path) -> None:
        assert self.conn
        await self.conn.executescript(schema.read_text()); await self.conn.commit()
    async def execute(self, sql: str, params: tuple[Any,...]=()) -> int:
        assert self.conn
        async with self.lock:
            cur=await self.conn.execute(sql,params); await self.conn.commit(); return cur.lastrowid
    async def fetchone(self, sql: str, params: tuple[Any,...]=()):
        assert self.conn
        cur=await self.conn.execute(sql,params); return await cur.fetchone()
    async def fetchall(self, sql: str, params: tuple[Any,...]=()):
        assert self.conn
        cur=await self.conn.execute(sql,params); return await cur.fetchall()
    async def close(self):
        if self.conn: await self.conn.close()
