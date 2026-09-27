from datetime import datetime
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton,InlineKeyboardMarkup
from pipeline.context import PipelineContext
async def run(ctx:PipelineContext,qid:int,movie:str,channel_id:int,qualities:list[str],link:str)->int:
 text=(f'🎬 **{movie}**\n\n🔊 **Audio:** Hindi\n⚡ **Available Qualities:** {" | ".join(qualities)}\n'
       f'📅 **Added:** {datetime.now().strftime("%d %B %Y")}\n\n👇 Tap the button below to download 👇')
 if ctx.cfg.owner_username:text+=f'\n\n📢 Powered by @{ctx.cfg.owner_username}'
 rows=[[InlineKeyboardButton('🚀 Download Movie',url=link)]]
 if ctx.cfg.tutorial_link:rows.append([InlineKeyboardButton('❓ How to Open Link',url=ctx.cfg.tutorial_link)])
 post=await ctx.speed.call(lambda:ctx.client.send_message(channel_id,text,parse_mode=ParseMode.MARKDOWN,reply_markup=InlineKeyboardMarkup(rows),disable_web_page_preview=True),qid)
 await ctx.speed.call(lambda:ctx.client.pin_chat_message(channel_id,post.id,disable_notification=True),qid)
 await ctx.db.patch_state(qid,final_post_id=post.id);return post.id
