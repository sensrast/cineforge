from telegram.ext import Application,CommandHandler,MessageHandler,CallbackQueryHandler,filters
from control.handlers import ControlHandlers
def build_control_bot(token:str,db,owner_id:int)->Application:
 app=Application.builder().token(token).build();h=ControlHandlers(db,owner_id)
 def own(fn):return h.owner(fn)
 for cmd,fn in [('start',h.start),('add',h.add),('batch',h.batch),('status',h.status),('settings',h.settings),('toggle_limits',h.toggle_limits),('logs',h.logs),('pause',h.pause),('resume',h.resume),('cancel',h.cancel),('retry',h.retry)]:app.add_handler(CommandHandler(cmd,own(fn)))
 app.add_handler(CallbackQueryHandler(own(h.callback),pattern=r'^cfg:'))
 app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,own(h.text)))
 return app
