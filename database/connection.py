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
        await self.conn.executescript(schema.read_text())
        for table in ("queue", "created_channels"):
            columns={row[1] for row in await (await self.conn.execute(f"PRAGMA table_info({table})")).fetchall()}
            if "content_type" not in columns:
                await self.conn.execute(f"ALTER TABLE {table} ADD COLUMN content_type TEXT NOT NULL DEFAULT 'movie'")
            if table == "queue" and "force_rebuild" not in columns:
                await self.conn.execute("ALTER TABLE queue ADD COLUMN force_rebuild INTEGER NOT NULL DEFAULT 0")
        state_columns={row[1] for row in await (await self.conn.execute("PRAGMA table_info(pipeline_state)")).fetchall()}
        if "backup_done" not in state_columns:
            await self.conn.execute("ALTER TABLE pipeline_state ADD COLUMN backup_done INTEGER DEFAULT 0")
        if "backup_message_ids_json" not in state_columns:
            await self.conn.execute("ALTER TABLE pipeline_state ADD COLUMN backup_message_ids_json TEXT DEFAULT '[]'")
        await self.conn.commit()
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
