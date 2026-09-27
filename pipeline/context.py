from dataclasses import dataclass
from pyrogram import Client
from config import Config
from database.queries import Queries
from userbot.speed_controller import SpeedController
@dataclass
class PipelineContext:
 client:Client; cfg:Config; db:Queries; speed:SpeedController
