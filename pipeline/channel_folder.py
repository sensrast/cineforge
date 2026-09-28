"""Maintain a Telegram dialog folder containing CineForge-created channels."""
from __future__ import annotations
import logging
log=logging.getLogger(__name__)
from pyrogram.raw.functions.messages import GetDialogFilters,UpdateDialogFilter
from pyrogram.raw.functions.chatlists import ExportChatlistInvite,EditExportedInvite,GetExportedInvites
from pyrogram.raw.types import DialogFilter,DialogFilterChatlist,InputChatlistDialogFilter
from pipeline.context import PipelineContext
from utils.github_store import persist_state
from utils.notifications import notify_control_bot

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
        custom_filters=[item for item in filters if isinstance(item,(DialogFilter,DialogFilterChatlist))]
        for item in custom_filters:
            if str(getattr(item,"title",""))==title:
                existing=item;break
        # If this account has one owner-created folder already, use it rather
        # than silently creating a second folder with a different default name.
        if existing is None and len(custom_filters)==1:
            existing=custom_filters[0];title=str(existing.title)
            await ctx.db.set_setting("created_channels_folder_name",title)
        used={int(getattr(item,"id",0) or 0) for item in filters}
        filter_id=int(existing.id) if existing else next((value for value in range(2,256) if value not in used),None)
        if filter_id is None:raise RuntimeError("No Telegram dialog-folder slot is available")
        pinned=list(existing.pinned_peers) if existing else []
        included=list(existing.include_peers) if existing else []
        excluded=list(getattr(existing,"exclude_peers",[]) or []) if existing else []
        known={_peer_key(peer) for peer in pinned+included}
        # String sessions do not retain Pyrogram's peer cache. Reading dialogs
        # once makes numeric -100... channel IDs resolvable after every restart.
        async for _dialog in ctx.client.get_dialogs(limit=500):
            pass
        for channel_id in channel_ids:
            try:peer=await ctx.speed.call(lambda cid=channel_id:ctx.client.resolve_peer(cid),qid)
            except Exception as exc:
                await ctx.db.log(f"Could not add channel {channel_id} to folder: {exc}","WARNING",qid);continue
            if _peer_key(peer) not in known:
                included.append(peer);known.add(_peer_key(peer))
        if isinstance(existing,DialogFilterChatlist):
            updated=DialogFilterChatlist(
                id=filter_id,title=title,pinned_peers=pinned,include_peers=included,
                has_my_invites=getattr(existing,"has_my_invites",None),emoticon=getattr(existing,"emoticon",None),
            )
        else:
            updated=DialogFilter(
                id=filter_id,title=title,pinned_peers=pinned,include_peers=included,exclude_peers=excluded,
                contacts=getattr(existing,"contacts",None),non_contacts=getattr(existing,"non_contacts",None),
                groups=getattr(existing,"groups",None),broadcasts=getattr(existing,"broadcasts",None),
                bots=getattr(existing,"bots",None),exclude_muted=getattr(existing,"exclude_muted",None),
                exclude_read=getattr(existing,"exclude_read",None),exclude_archived=getattr(existing,"exclude_archived",None),
                emoticon=getattr(existing,"emoticon",None),
            )
        await ctx.speed.call(lambda:ctx.client.invoke(UpdateDialogFilter(id=filter_id,filter=updated)),qid)

        # Keep a shareable Telegram chat-folder invite synchronized with the
        # same peers. If the owner already exported this folder, update that
        # invite; otherwise create it once and save its t.me/addlist URL.
        chatlist=InputChatlistDialogFilter(filter_id=filter_id)
        exported=await ctx.speed.call(lambda:ctx.client.invoke(GetExportedInvites(chatlist=chatlist)),qid)
        peers=pinned+included
        if getattr(exported,"invites",None):
            invite=exported.invites[0]
            slug=invite.url.rstrip("/").rsplit("/",1)[-1]
            result=await ctx.speed.call(lambda:ctx.client.invoke(EditExportedInvite(chatlist=chatlist,slug=slug,title=title,peers=peers)),qid)
            folder_url=result.url
        else:
            result=await ctx.speed.call(lambda:ctx.client.invoke(ExportChatlistInvite(chatlist=chatlist,title=title,peers=peers)),qid)
            folder_url=result.invite.url
        previous=await ctx.db.setting("created_channels_folder_link","")
        await ctx.db.set_setting("created_channels_folder_link",folder_url)
        await persist_state(ctx.db)
        if folder_url!=previous:
            try:await notify_control_bot(ctx.cfg.control_token,ctx.cfg.owner_id,f"📁 Created-channels folder link:\n{folder_url}")
            except Exception:pass
        await ctx.db.log(f"Updated shareable Telegram folder '{title}' with {len(peers)} channels: {folder_url}","INFO",qid)
        return True
    except Exception as exc:
        log.exception("Created-channels folder update failed")
        await ctx.db.log(f"Created-channels folder update failed: {exc}","WARNING",qid)
        return False
