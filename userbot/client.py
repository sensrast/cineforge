from pyrogram import Client
from config import Config

def build_userbot(cfg:Config)->Client:
 return Client('cineforge_userbot',api_id=cfg.api_id,api_hash=cfg.api_hash,session_string=cfg.session_string,in_memory=True,no_updates=False)
