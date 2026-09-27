from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from control.handlers import ControlHandlers

def build_control_bot(token: str, db, owner_id: int, cfg, runtime, login) -> Application:
    app = Application.builder().token(token).build()
    handlers = ControlHandlers(db, owner_id, cfg, runtime, login)
    own = handlers.owner
    commands = [
        ("start", handlers.start), ("add", handlers.add), ("movie", handlers.movie), ("series", handlers.series), ("batch", handlers.batch),
        ("status", handlers.status), ("settings", handlers.settings),
        ("toggle_limits", handlers.toggle_limits), ("logs", handlers.logs),
        ("pause", handlers.pause), ("resume", handlers.resume),
        ("cancel", handlers.cancel), ("retry", handlers.retry),
        ("cancel_login", handlers.cancel_login),
    ]
    for command, callback in commands:
        app.add_handler(CommandHandler(command, own(callback)))
    app.add_handler(CallbackQueryHandler(own(handlers.callback), pattern=r"^(auth|nav|cfg|job|addmode|type|batchtype):"))
    app.add_handler(MessageHandler(filters.Sticker.ALL, own(handlers.sticker)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, own(handlers.text)))
    return app
