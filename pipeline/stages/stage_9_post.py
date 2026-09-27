"""Replace temporary batch messages with stickers and one final download post."""
from __future__ import annotations
import asyncio
from datetime import datetime
from pipeline.context import PipelineContext
from utils.notifications import (
    send_download_post, edit_download_post, bot_api_request, send_channel_sticker,
)

async def _post_exists(ctx: PipelineContext, channel_id: int, message_id: int | None) -> bool:
    if not message_id:return False
    try:
        message=await ctx.client.get_messages(channel_id,int(message_id))
        return bool(message and message.id and not getattr(message,"empty",False))
    except Exception:return False

async def _remove_pin_notification(ctx:PipelineContext,qid:int,channel_id:int,post_id:int)->None:
    for _ in range(6):
        ids=[]
        async for message in ctx.client.get_chat_history(channel_id,limit=10):
            if message.id>=post_id and message.id!=post_id and (getattr(message,"service",None) or getattr(message,"pinned_message",None)):
                ids.append(message.id)
        if ids:
            await ctx.speed.call(lambda:ctx.client.delete_messages(channel_id,ids),qid)
            await ctx.db.log("Deleted automatic pin notification message","INFO",qid);return
        await asyncio.sleep(.5)

async def _delete_temporary_messages(ctx:PipelineContext,qid:int,channel_id:int,files:list[dict])->None:
    ids=set()
    for item in files:
        for key in ("sticker_message_id","channel_message_id","end_sticker_message_id"):
            if item.get(key):ids.add(int(item[key]))
    if ids:
        try:
            await ctx.speed.call(lambda:ctx.client.delete_messages(channel_id,sorted(ids)),qid)
            await ctx.db.log(f"Deleted {len(ids)} temporary batch messages","INFO",qid)
        except Exception as exc:await ctx.db.log(f"Temporary-message cleanup failed: {exc}","WARNING",qid)

async def run(ctx:PipelineContext,qid:int,movie:str,channel_id:int,copied_files:list[dict],link:str)->int:
    order={"480p":0,"720p":1,"1080p":2,"2160p":3}
    qualities=sorted({item["quality"] for item in copied_files},key=lambda q:order.get(q,99))
    episodes={(item.get("season"),item.get("episode")) for item in copied_files if item.get("episode") is not None}
    text=(f"🎬 {movie}\n\n🔊 Audio: Hindi\n⚡ Available Qualities: {' | '.join(qualities)}\n"
          +(f"📺 Episodes: {len(episodes)}\n" if episodes else "")
          +f"📅 Added: {datetime.now().strftime('%d %B %Y')}\n\n👇 Tap the button below to download 👇")
    if ctx.cfg.owner_username:text+=f"\n\n📢 Powered by @{ctx.cfg.owner_username.lstrip('@')}"

    start_sticker=await ctx.db.setting("sticker_start","")
    end_sticker=await ctx.db.setting("sticker_end","")
    if not start_sticker or not end_sticker:raise RuntimeError("Configure Final Starting Sticker and End Sticker in settings")

    # The batch link is already generated. Remove all quality stickers, files,
    # and the temporary batch-end sticker before creating the final layout.
    await _delete_temporary_messages(ctx,qid,channel_id,copied_files)

    state=await ctx.db.state(qid)
    existing_id=int(state["final_post_id"]) if state and state["final_post_id"] else None
    exists=await _post_exists(ctx,channel_id,existing_id)
    if exists:
        try:
            await edit_download_post(ctx.cfg.control_token,channel_id,existing_id,text,link,ctx.cfg.tutorial_link)
            post_id=existing_id
            await ctx.db.log("Existing download post updated; final stickers not duplicated","INFO",qid)
        except Exception:
            await bot_api_request(ctx.cfg.control_token,"deleteMessage",{"chat_id":channel_id,"message_id":existing_id})
            await send_channel_sticker(ctx.cfg.control_token,channel_id,start_sticker)
            post_id=await send_download_post(ctx.cfg.control_token,channel_id,text,link,ctx.cfg.tutorial_link)
            await ctx.db.patch_state(qid,final_post_id=post_id)
            await _remove_pin_notification(ctx,qid,channel_id,post_id)
            await send_channel_sticker(ctx.cfg.control_token,channel_id,end_sticker)
    else:
        await send_channel_sticker(ctx.cfg.control_token,channel_id,start_sticker)
        post_id=await send_download_post(ctx.cfg.control_token,channel_id,text,link,ctx.cfg.tutorial_link)
        await ctx.db.patch_state(qid,final_post_id=post_id)
        try:await _remove_pin_notification(ctx,qid,channel_id,post_id)
        except Exception as exc:await ctx.db.log(f"Pin-notification cleanup failed: {exc}","WARNING",qid)
        await send_channel_sticker(ctx.cfg.control_token,channel_id,end_sticker)
        await ctx.db.log("Sent final start sticker, download post, and end sticker","INFO",qid)
    return post_id
