"""Isolated updates-channel promotion via an external link-provider bot."""
from __future__ import annotations
import re
import asyncio
import time
from pipeline.context import PipelineContext
from utils.notifications import bot_api_request
from utils.text_parser import format_template

URL_RE=re.compile(r"https?://[^\s<>]+",re.I)

def _urls(message)->list[str]:
    values=URL_RE.findall((message.text or message.caption or ""))
    markup=message.reply_markup
    if markup and getattr(markup,"inline_keyboard",None):
        for row in markup.inline_keyboard:
            for button in row:
                if button.url:values.append(button.url)
    return [value.rstrip(').,]') for value in values]

def _fingerprint(message)->tuple:
    buttons=[]
    markup=message.reply_markup
    if markup and getattr(markup,"inline_keyboard",None):
        for row in markup.inline_keyboard:
            buttons.extend((button.text or "",button.url or "",str(button.callback_data or "")) for button in row)
    return (message.text or message.caption or "",str(message.edit_date or ""),tuple(buttons))

async def _snapshot(client,chat)->dict[int,tuple]:
    result={}
    async for message in client.get_chat_history(chat,limit=20):
        if not message.outgoing:result[message.id]=_fingerprint(message)
    return result

async def _wait_provider_url(ctx,chat,before:dict[int,tuple])->str:
    deadline=time.monotonic()+max(60,ctx.cfg.flow_timeout)
    while time.monotonic()<deadline:
        async for message in ctx.client.get_chat_history(chat,limit=20):
            if message.outgoing:continue
            changed=message.id not in before or before[message.id]!=_fingerprint(message)
            links=_urls(message)
            if changed and links:return links[0]
        await asyncio.sleep(.5)
    raise TimeoutError("Link provider did not return a generated URL")

async def run(ctx:PipelineContext,qid:int,movie:str,channel_id:int,invite_link:str)->int|None:
    if (await ctx.db.setting("promotion_enabled","false")).lower()!="true":return None
    state=await ctx.db.state(qid)
    if state and state["promotion_done"]:return int(state["promotion_post_id"] or 0) or None
    image=await ctx.db.setting("promotion_image","")
    updates=await ctx.db.setting("promotion_updates_channel","@In_hindi_dubbed_movies")
    provider=(await ctx.db.setting("promotion_link_provider","Link_providerobot")).lstrip("@")
    if not image:raise RuntimeError("Updates Promotion is enabled but Promotion Image is not configured")
    if not updates:raise RuntimeError("Updates Promotion is enabled but Updates Channel is not configured")

    generated=(state["promotion_link"] if state else None) or ""
    temporary_id=None
    try:
        if not generated:
            temporary=await bot_api_request(ctx.cfg.control_token,"sendPhoto",{
                "chat_id":channel_id,"photo":image,"caption":invite_link,
            })
            temporary_id=int(temporary["message_id"])
            provider_chat="@"+provider
            await ctx.speed.call(lambda:ctx.client.send_message(provider_chat,"/genlink"),qid)
            # Give the provider's command acknowledgement time to arrive so the
            # subsequent URL wait belongs to the forwarded image.
            await asyncio.sleep(1)
            before=await _snapshot(ctx.client,provider_chat)
            await ctx.speed.call(lambda:ctx.client.forward_messages(provider_chat,channel_id,temporary_id),qid)
            generated=await _wait_provider_url(ctx,provider_chat,before)
            await ctx.db.patch_state(qid,promotion_link=generated)

        caption_template=await ctx.db.setting("promotion_caption","❤️‍🔥 {movie}\n\n🥳 all qualities Added ....!🕺")
        caption=format_template(caption_template,movie=movie,owner_username=ctx.cfg.owner_username)
        button=await ctx.db.setting("promotion_button_text","Click here to start and get Movie")
        result=await bot_api_request(ctx.cfg.control_token,"sendPhoto",{
            "chat_id":updates,"photo":image,"caption":caption,
            "reply_markup":{"inline_keyboard":[[{"text":button,"url":generated}],[{"text":button,"url":generated}]]},
        })
        post_id=int(result["message_id"])
        await ctx.db.patch_state(qid,promotion_done=1,promotion_post_id=post_id,promotion_link=generated)
        await ctx.db.log(f"Published updates promotion to {updates}","INFO",qid)
        return post_id
    finally:
        if temporary_id:
            try:await bot_api_request(ctx.cfg.control_token,"deleteMessage",{"chat_id":channel_id,"message_id":temporary_id})
            except Exception as exc:await ctx.db.log(f"Promotion temporary-image cleanup failed: {exc}","WARNING",qid)
