"""Interactive one-time Pyrogram string-session generator."""
from __future__ import annotations
from pyrogram import Client
from config import Config
async def generate_session(cfg:Config)->str:
 if not cfg.api_id or not cfg.api_hash or not cfg.phone: raise RuntimeError('API_ID, API_HASH and USERBOT_PHONE are required')
 c=Client('cineforge_login',api_id=cfg.api_id,api_hash=cfg.api_hash,phone_number=cfg.phone,in_memory=True)
 await c.start()
 try:return await c.export_session_string()
 finally:await c.stop()
