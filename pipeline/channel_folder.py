"""Maintain a Telegram dialog folder containing CineForge-created channels."""
from __future__ import annotations
from pyrogram.raw.functions.messages import GetDialogFilters,UpdateDialogFilter
from pyrogram.raw.types import DialogFilter
from pipeline.context import PipelineContext

def _peer_key(peer):
    for name in ("channel_id","chat_id","user_id"):
        value=getattr(peer,name,None)
        if value is not None:return (peer.__class__.__name__,int(value))
    return (peer.__class__.__name__,repr(peer))

async def ensure_created_channels_folder(ctx:PipelineContext,channel_ids:list[int],qid:int|None=None)->bool:
    if (await ctx.db.setting("created_channels_folder_enabled","true")).lower()!="true":return False
    title=await ctx.db.setting("created_channels_folder_name","🎬 Movie Channels")
    try:
        filters=await ctx.speed.call(lambda:ctx.client.invoke(GetDialogFilters()),qid)
        existing=None
        for item in filters:
            if isinstance(item,DialogFilter) and str(getattr(item,"title",""))==title:
                existing=item;break
        used={int(getattr(item,"id",0) or 0) for item in filters}
        filter_id=int(existing.id) if existing else next((value for value in range(2,256) if value not in used),None)
        if filter_id is None:raise RuntimeError("No Telegram dialog-folder slot is available")
        pinned=list(existing.pinned_peers) if existing else []
        included=list(existing.include_peers) if existing else []
        excluded=list(existing.exclude_peers) if existing else []
        known={_peer_key(peer) for peer in pinned+included}
        for channel_id in channel_ids:
            try:peer=await ctx.speed.call(lambda cid=channel_id:ctx.client.resolve_peer(cid),qid)
            except Exception as exc:
                await ctx.db.log(f"Could not add channel {channel_id} to folder: {exc}","WARNING",qid);continue
            if _peer_key(peer) not in known:
                included.append(peer);known.add(_peer_key(peer))
        updated=DialogFilter(
            id=filter_id,title=title,pinned_peers=pinned,include_peers=included,exclude_peers=excluded,
            contacts=getattr(existing,"contacts",None),non_contacts=getattr(existing,"non_contacts",None),
            groups=getattr(existing,"groups",None),broadcasts=getattr(existing,"broadcasts",None),
            bots=getattr(existing,"bots",None),exclude_muted=getattr(existing,"exclude_muted",None),
            exclude_read=getattr(existing,"exclude_read",None),exclude_archived=getattr(existing,"exclude_archived",None),
            emoticon=getattr(existing,"emoticon",None),
        )
        await ctx.speed.call(lambda:ctx.client.invoke(UpdateDialogFilter(id=filter_id,filter=updated)),qid)
        await ctx.db.log(f"Updated Telegram folder '{title}' with {len(included)+len(pinned)} created channels","INFO",qid)
        return True
    except Exception as exc:
        await ctx.db.log(f"Created-channels folder update failed: {exc}","WARNING",qid)
        return False
