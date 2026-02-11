import logging
import os
import shutil
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    filters, ConversationHandler, CallbackQueryHandler, ContextTypes,
    InlineQueryHandler, TypeHandler, Application
)

from config import Config
from database.connection import init_db

from handlers.start import start

from utils.states import SELECT_ACTION, WAITING_INPUT, WAITING_COVER, WAITING_CHANNEL

from handlers.editor import (
    start_editor, 
    handle_button_click, 
    receive_new_value, 
    receive_cover, 
    receive_channel,
    cancel_command, 
    handle_timeout,
    inline_query_handler
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def clear_downloads():
    folder = 'downloads'
    if not os.path.exists(folder):
        os.makedirs(folder)
        return

    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')
    print("Downloads folder cleared.")

async def start_over_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try: await query.message.delete()
    except: pass
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="✨ **بسیار عالی!**\n\nآهنگ بعدی را بفرست تا با هم ادیتش کنیم. منتظرم... 🎧",
        parse_mode='Markdown'
    )

async def global_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⚠️ این نشست منقضی شده است.", show_alert=True)

def main():
    print("Initializing database and clearing downloads...")
    init_db()
    clear_downloads()

    app = (
        ApplicationBuilder()
        .token(Config.BOT_TOKEN)
        .read_timeout(30) 
        .write_timeout(30) 
        .connect_timeout(30)
        .pool_timeout(30)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.AUDIO, start_editor)],
        states={
            SELECT_ACTION: [CallbackQueryHandler(handle_button_click)],
            WAITING_INPUT: [
                CallbackQueryHandler(handle_button_click),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_value)
            ],
            WAITING_COVER: [
                CallbackQueryHandler(handle_button_click),
                MessageHandler(filters.PHOTO, receive_cover)
            ],
            WAITING_CHANNEL: [
                CallbackQueryHandler(handle_button_click),
                MessageHandler(filters.TEXT | filters.FORWARDED, receive_channel)
            ],
            ConversationHandler.TIMEOUT: [TypeHandler(Update, handle_timeout)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command)
        ],
        allow_reentry=True,
        conversation_timeout=60 
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(start_over_callback, pattern='^start_over$'))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(CallbackQueryHandler(global_button_handler))

    print("BOT IS RUNNING...")
    app.run_polling()

if __name__ == '__main__':
    main()