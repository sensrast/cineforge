"""Optional server-side media backup to a private Telegram channel."""
from __future__ import annotations
from pipeline.context import PipelineContext

def _destination(value: str):
    value=value.strip()
    if value.startswith("https://t.me/"):
        value="@"+value.rstrip("/").rsplit("/",1)[-1]
    if value.lstrip("-").isdigit():return int(value)
    return value if value.startswith("@") else "@"+value.lstrip("@")

async def backup_movie(ctx:PipelineContext,qid:int,movie:str,source_channel_id:int,files:list[dict],batch_link:str)->list[int]:
    enabled=(await ctx.db.setting("backup_enabled","false")).lower()=="true"
    if not enabled:return []
    state=await ctx.db.state(qid)
    if state and state["backup_done"]:return []
    raw=await ctx.db.setting("backup_channel","")
    if not raw:raise RuntimeError("Backup Storage is enabled but Backup Channel is not configured")
    target=_destination(raw)
    chat=await ctx.speed.call(lambda:ctx.client.get_chat(target),qid)
    target_id=chat.id
    qualities=sorted({item['quality'] for item in files},key=lambda q:{'480p':0,'720p':1,'1080p':2,'2160p':3}.get(q,99))
    header=await ctx.speed.call(lambda:ctx.client.send_message(target_id,f"🎬 {movie}\n⚡ {' | '.join(qualities)}\n🔗 Batch: {batch_link}"),qid)
    saved=[header.id]
    for item in files:
        episode_label=f"S{int(item.get('season') or 1):02d}E{int(item['episode']):02d}" if item.get('episode') is not None else ""
        caption=f"🎬 {movie}\n"
        if episode_label:caption+=f"📺 {episode_label}\n"
        caption+=f"⚡ {item['quality']}\n🔗 Batch: {batch_link}"
        if ctx.cfg.owner_username:caption+=f"\n📢 @{ctx.cfg.owner_username.lstrip('@')}"
        copied=await ctx.speed.call(lambda i=item,c=caption:ctx.client.copy_message(target_id,source_channel_id,i['channel_message_id'],caption=c),qid)
        saved.append(copied.id)
        await ctx.speed.delay()
    await ctx.db.patch_state(qid,backup_done=1,backup_message_ids_json=saved)
    await ctx.db.log(f"Backed up {len(files)} media files to {target_id}","INFO",qid)
    return saved
