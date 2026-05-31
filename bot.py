import logging
import os
import shutil
import re
from telegram import InlineKeyboardMarkup, Update, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, 
    filters, ConversationHandler, CallbackQueryHandler, ContextTypes,
    InlineQueryHandler, TypeHandler, Application, ChatMemberHandler
)
from config import Config
from database.user_service import initialize_database, get_locked_channels
from handlers.settings import settings_panel, settings_callback, receive_preset_value, SETTINGS_MENU, WAITING_PRESET_VALUE, WAITING_SETTINGS_CHANNEL   
from handlers.start import start, initial_language_selection, help_support_callback
from utils.states import SELECT_ACTION, WAITING_INPUT, WAITING_COVER, WAITING_CHANNEL
from handlers.editor import (
    start_editor, handle_button_click, receive_new_value, receive_cover, receive_channel,
    cancel_command, handle_timeout, inline_query_handler
)
from handlers.admin import (
    admin_panel, admin_callback, process_broadcast, cancel_broadcast,
    set_lock_channel, ADMIN_MENU, BROADCAST_REQUEST, WAITING_LOCK_CHANNEL
)
from handlers.youtube import handle_youtube_link, process_youtube_callback
from handlers.instagram import handle_instagram_link, process_instagram_callback
from handlers.soundcloud import handle_soundcloud_link, process_soundcloud_callback

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
            pass

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

async def get_unjoined_channels(user_id, context):
    locked_channels = get_locked_channels()
    if not locked_channels:
        return []
    not_joined = []
    for ch_id, title, link in locked_channels:
        try:
            member = await context.bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append((title, link))
        except Exception:
            not_joined.append((title, link))
    return not_joined

def build_lock_keyboard(unjoined_channels):
    keyboard = []
    for title, link in unjoined_channels:
        display_title = title if len(title) < 25 else title[:22] + "..."
        keyboard.append([InlineKeyboardButton(f"📣 {display_title}", url=link)])
    keyboard.append([InlineKeyboardButton("🔄 بررسی عضویت", callback_data="check_join_status")])
    return InlineKeyboardMarkup(keyboard)

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    unjoined = await get_unjoined_channels(user_id, context)
    if not unjoined:
        return True
    reply_markup = build_lock_keyboard(unjoined)
    msg_text = (
        "🔒 **دسترسی محدود شده است**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👋 کاربر گرامی، جهت حمایت از ما و استفاده رایگان از ربات، لطفاً در کانال‌های اسپانسر عضو شوید.\n\n"
        "✅ **به محض عضویت، این پیام خودکار محو می‌شود.**"
    )
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception: 
            pass
    elif update.message:
        msg = await context.bot.send_message(chat_id=user_id, text=msg_text, reply_markup=reply_markup, parse_mode='Markdown')
        context.bot_data[f"lock_msg_{user_id}"] = msg.message_id
    return False

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    is_fully_joined = await check_membership(update, context)
    if is_fully_joined:
        await query.answer("✅ عضویت تایید شد! خوش آمدید.", show_alert=True)
        try: 
            await query.message.delete() 
        except Exception: 
            pass
        await context.bot.send_message(update.effective_chat.id, "🎉 حالا می‌تونی آهنگت رو بفرستی!")
    else:
        await query.answer("❌ هنوز در تمام کانال‌ها عضو نشده‌اید!", show_alert=True)

async def protected_start_editor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_membership(update, context):
        return await start_editor(update, context)
    return ConversationHandler.END

async def protected_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_membership(update, context):
        return await handle_youtube_link(update, context)
    return ConversationHandler.END

async def protected_instagram_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_membership(update, context):
        return await handle_instagram_link(update, context)
    return ConversationHandler.END

async def protected_soundcloud_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await check_membership(update, context):
        return await handle_soundcloud_link(update, context)
    return ConversationHandler.END

async def auto_check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result: 
        return
    user_id = result.from_user.id
    new_status = result.new_chat_member.status
    if new_status not in ['member', 'administrator', 'creator']:
        return
    lock_msg_id = context.bot_data.get(f"lock_msg_{user_id}")
    if not lock_msg_id: 
        return 
    unjoined = await get_unjoined_channels(user_id, context)
    if not unjoined:
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=lock_msg_id)
            del context.bot_data[f"lock_msg_{user_id}"] 
        except Exception: 
            pass
        await context.bot.send_message(
            chat_id=user_id, 
            text="🎉 **عضویت شما تایید شد!**\nاکنون می‌توانید فایل خود را ارسال کنید. 🎧",
            parse_mode='Markdown'
        )
    else:
        try:
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=lock_msg_id,
                text=(
                    "🔒 **دسترسی محدود شده است**\n"
                    "━━━━━━━━━━━━━━━━━━━━\n"
                    "🙏 **هنوز تمام نشده!**\n"
                    "لطفاً در کانال‌های باقی‌مانده نیز عضو شوید:\n\n"
                    "✅ **به محض تکمیل، قفل باز می‌شود.**"
                ),
                reply_markup=build_lock_keyboard(unjoined),
                parse_mode='Markdown'
            )
        except Exception: 
            pass

def main():
    initialize_database()
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
    admin_conv = ConversationHandler(
        entry_points=[
            CommandHandler('admin', admin_panel)
        ],
        states={
            ADMIN_MENU: [
                CallbackQueryHandler(admin_callback, pattern='^(back_to_main|admin_lock_menu|add_lock_channel|unlock_.*|admin_stats|admin_broadcast|admin_backup|admin_clean|close_panel)$')
            ],
            BROADCAST_REQUEST: [
                CallbackQueryHandler(admin_callback, pattern='^(back_to_main|close_panel)$'),
                MessageHandler(filters.ALL & ~filters.COMMAND, process_broadcast)
            ],
            WAITING_LOCK_CHANNEL: [
                CallbackQueryHandler(admin_callback, pattern='^(admin_lock_menu|close_panel)$'), 
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_lock_channel)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', cancel_broadcast),
            CallbackQueryHandler(admin_callback, pattern='^close_panel$')
        ],
        allow_reentry=True,
        per_message=False
    )
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.AUDIO, protected_start_editor),
            MessageHandler(filters.Regex(r'(?i)^(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+'), protected_youtube_link),
            MessageHandler(filters.Regex(r'(?i)^(https?://)?(www\.)?(instagram\.com|instagr\.am)/.+'), protected_instagram_link),
            MessageHandler(filters.Regex(r'(?i)^(https?://)?(www\.|m\.|on\.)?soundcloud\.com/.+'), protected_soundcloud_link)
        ],
        states={
            SELECT_ACTION: [
                CallbackQueryHandler(process_youtube_callback, pattern='^ytdl_'),
                CallbackQueryHandler(process_instagram_callback, pattern='^igdl_'),
                CallbackQueryHandler(process_soundcloud_callback, pattern='^scdl_'),
                CallbackQueryHandler(handle_button_click, pattern='^(goto_advanced|goto_main|cancel|done|manage_channels|mode_delete|mode_view|add_new_channel|toggle_ch_.*|del_ch_.*|start_cut|menu_convert|menu_lock|convert_to_voice|convert_.*|pro_clean|toggle_lock_.*|auto_rename|detect_lang|edit_.*)$')
            ],
            WAITING_INPUT: [
                CallbackQueryHandler(handle_button_click, pattern='^(goto_advanced|goto_main|cancel)$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_value)
            ],
            WAITING_COVER: [
                CallbackQueryHandler(handle_button_click, pattern='^(goto_advanced|goto_main|cancel)$'),
                MessageHandler(filters.PHOTO, receive_cover)
            ],
            WAITING_CHANNEL: [
                CallbackQueryHandler(handle_button_click, pattern='^(goto_advanced|goto_main|cancel|mode_view)$'),
                MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.FORWARDED, receive_channel)
            ],
            ConversationHandler.TIMEOUT: [TypeHandler(Update, handle_timeout)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_command)
        ],
        allow_reentry=True,
        conversation_timeout=3600,
        per_message=False
    )
    settings_conv = ConversationHandler(
        entry_points=[
            CommandHandler('settings', settings_panel) , 
            CallbackQueryHandler(settings_panel, pattern='^open_settings$')
        ],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(settings_callback, pattern='^(toggle_language|manage_channels_settings|toggle_ch_set_.*|del_ch_set_.*|mode_delete_settings|mode_view_settings|add_new_channel_settings|back_to_main_settings|close_settings|ignore|toggle_fast_mode|set_preset_.*|back_to_settings)$')
            ],
            WAITING_PRESET_VALUE: [
                CallbackQueryHandler(settings_callback, pattern='^(back_to_settings|close_settings)$'), 
                MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.PHOTO, receive_preset_value)
            ],
            WAITING_SETTINGS_CHANNEL: [
                CallbackQueryHandler(settings_callback, pattern='^(manage_channels_settings|close_settings)$'), 
                MessageHandler((filters.TEXT & ~filters.COMMAND) | filters.FORWARDED, receive_channel)
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel_command)], 
        allow_reentry=True,
        per_message=False
    )
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern='^check_join_status$'))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(initial_language_selection, pattern='^set_lang_'))
    app.add_handler(CallbackQueryHandler(help_support_callback, pattern='^(help|support|back_start)$'))
    app.add_handler(settings_conv)
    app.add_handler(CommandHandler('settings', settings_panel))
    app.add_handler(ChatMemberHandler(auto_check_join, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(admin_conv)
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(start_over_callback, pattern='^start_over$'))
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(CallbackQueryHandler(global_button_handler))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
