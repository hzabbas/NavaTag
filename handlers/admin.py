import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import Config
from database.user_service import (
    get_total_users_count, 
    get_all_users_id, 
    add_locked_channel, 
    remove_locked_channel, 
    get_locked_channels
)

ADMIN_MENU, BROADCAST_REQUEST, WAITING_LOCK_CHANNEL = range(3)

def get_admin_keyboard():
   
    locks = get_locked_channels()
    lock_status = f"{len(locks)} کانال" if locks else "❌ غیرفعال"

    keyboard = [
        [
            InlineKeyboardButton("📊 آمار ربات", callback_data='admin_stats'),
           
            InlineKeyboardButton(f"🔒 قفل کانال ({lock_status})", callback_data='admin_lock_menu')
        ],
        [
            InlineKeyboardButton("📢 پیام همگانی", callback_data='admin_broadcast'),
            InlineKeyboardButton("📥 دانلود دیتابیس", callback_data='admin_backup')
        ],
        [
            InlineKeyboardButton("🧹 پاکسازی سرور", callback_data='admin_clean'),
            InlineKeyboardButton("❌ بستن پنل", callback_data='close_panel')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_locks_keyboard():
    locks = get_locked_channels()
    keyboard = []
    
   
    for ch_id, title, link in locks:
       
        display_title = (title[:15] + '..') if len(title) > 15 else title
        keyboard.append([
            InlineKeyboardButton(f"🗑 حذف: {display_title}", callback_data=f"unlock_{ch_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("➕ افزودن کانال جدید", callback_data='add_lock_channel')])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='back_to_main')])
    
    return InlineKeyboardMarkup(keyboard)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return ConversationHandler.END

    await update.message.reply_text(
        "👤 **پنل مدیریت پیشرفته**\nبه تنظیمات خوش آمدید.",
        reply_markup=get_admin_keyboard(),
        parse_mode='Markdown'
    )
    return ADMIN_MENU

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != Config.ADMIN_ID:
        await query.answer("⛔️", show_alert=True)
        return ConversationHandler.END

    data = query.data

    if data == 'back_to_main':
        await query.edit_message_text(
            "👤 **پنل مدیریت**\nیکی از گزینه‌ها را انتخاب کنید:",
            reply_markup=get_admin_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_MENU

    if data == 'admin_lock_menu':
        await query.edit_message_text(
            "🔒 **مدیریت قفل کانال (Force Join)**\n\n"
            "لیست کانال‌هایی که کاربر مجبور به عضویت در آن‌هاست:",
            reply_markup=get_locks_keyboard(),
            parse_mode='Markdown'
        )
        return ADMIN_MENU

    if data == 'add_lock_channel':
        msg = await query.edit_message_text(
            "➕ **افزودن کانال قفل**\n\n"
            "برای اضافه کردن کانال، یکی از کارهای زیر را انجام دهید:\n"
            "1️⃣ آیدی عمومی کانال را بفرستید (مثال: `@MyChannel`)\n"
            "2️⃣ یک پیام از **کانال خصوصی** به اینجا فوروارد کنید.\n\n"
            "⚠️ **نکته:** ربات باید در آن کانال **ادمین** باشد.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data='admin_lock_menu')]]),
            parse_mode='Markdown'
        )
        context.user_data['lock_instruction_msg_id'] = msg.message_id
        return WAITING_LOCK_CHANNEL

 
    if data.startswith('unlock_'):
        ch_id = data.replace('unlock_', '')
        remove_locked_channel(ch_id)
        await query.answer("🗑 کانال از لیست قفل حذف شد.", show_alert=True)
        
        await query.edit_message_reply_markup(reply_markup=get_locks_keyboard())
        return ADMIN_MENU

    
    if data == 'admin_stats':
        count = get_total_users_count()
       
        try:
            folder_size = sum(os.path.getsize(os.path.join('downloads', f)) for f in os.listdir('downloads') if os.path.isfile(os.path.join('downloads', f)))
            folder_size_mb = folder_size / (1024 * 1024)
        except: folder_size_mb = 0
        
        await query.answer()
        await query.edit_message_text(
             f"📊 **آمار ربات**\n👥 کاربران: `{count}`\n📂 حجم فایل‌ها: `{folder_size_mb:.2f} MB`",
             reply_markup=get_admin_keyboard(),
             parse_mode='Markdown'
        )
        return ADMIN_MENU
    
    elif data == 'admin_broadcast':
        await query.answer()
        await query.edit_message_text(
            "📢 **پیام همگانی**\nپیامتان را بفرستید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]])
        )
        return BROADCAST_REQUEST
    
    elif data == 'admin_backup':
        await query.answer("ارسال دیتابیس...")
        if os.path.exists('bot_database.db'):
            await context.bot.send_document(user_id, open('bot_database.db', 'rb'), filename="backup.db")
        return ADMIN_MENU

    elif data == 'admin_clean':
        await query.answer("در حال پاکسازی...")
        
        folder = 'downloads'
        try:
            for f in os.listdir(folder):
                os.unlink(os.path.join(folder, f))
        except: pass
        await query.answer("✅ پاکسازی شد.", show_alert=True)
        return await admin_callback(update, context) 

    elif data == 'close_panel':
        await query.answer("بسته شد")
        await query.message.delete()
        return ConversationHandler.END

async def set_lock_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = update.effective_chat.id
    

    try: await msg.delete()
    except: pass

    target_chat_id = None
    

    if msg.forward_origin:
        if msg.forward_origin.type == 'channel':
            target_chat_id = msg.forward_origin.chat.id
        else:
            temp = await context.bot.send_message(chat_id, "❌ این پیام از کانال نیست!")
            await asyncio.sleep(3)
            try: await temp.delete()
            except: pass
            return WAITING_LOCK_CHANNEL
    else:
        text = msg.text.strip()
        if text.startswith('@') or text.startswith('-100') or text.isdigit():
            target_chat_id = text
        else:
            temp = await context.bot.send_message(chat_id, "❌ آیدی نامعتبر! (باید با @ شروع شود یا فوروارد باشد)")
            await asyncio.sleep(3)
            try: await temp.delete()
            except: pass
            return WAITING_LOCK_CHANNEL


    try:
        
        chat_info = await context.bot.get_chat(target_chat_id)
        
        
        bot_member = await context.bot.get_chat_member(target_chat_id, context.bot.id)
        if bot_member.status != 'administrator':
            raise Exception("Bot is not admin")

        
        invite_link = chat_info.invite_link
        if not invite_link:
            invite_link = await context.bot.export_chat_invite_link(target_chat_id)

       
        add_locked_channel(chat_info.id, chat_info.title, invite_link)

        instruct_id = context.user_data.get('lock_instruction_msg_id')
        if instruct_id:
            try: await context.bot.delete_message(chat_id, instruct_id)
            except: pass
            context.user_data['lock_instruction_msg_id'] = None
            
        safe_title = chat_info.title.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
        success = await context.bot.send_message(
            chat_id,
            f"✅ کانال **{safe_title}** به لیست قفل اضافه شد.",
            parse_mode='Markdown'
        )
        await asyncio.sleep(3)
        try: await success.delete()
        except: pass

        await admin_panel(update, context)
        return ADMIN_MENU

    except Exception as e:
        err_text = "❌ خطا: ربات در کانال ادمین نیست یا آیدی اشتباه است."
        if "Not found" in str(e): err_text = "❌ کانال پیدا نشد."
        
        temp = await context.bot.send_message(chat_id, err_text)
        await asyncio.sleep(4)
        try: await temp.delete()
        except: pass
        return WAITING_LOCK_CHANNEL


async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID: return ConversationHandler.END

    users = get_all_users_id()
    if not users:
        await update.message.reply_text("❌ کاربری یافت نشد.")
        return ADMIN_MENU


    status_msg = await update.message.reply_text(f"⏳ در حال ارسال به {len(users)} کاربر...\nلطفاً صبر کنید.")
    success = 0
    blocked = 0

    for uid in users:
        try:
            
            await update.message.copy(chat_id=uid)
            success += 1
            await asyncio.sleep(0.05) 
        except:
            blocked += 1
    

    report_text = (
        f"📢 **گزارش پایان پیام همگانی**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 **جامعه آماری:** `{len(users)}` کاربر\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ **ارسال موفق:** `{success}`\n"
        f"⛔️ **بلاک/ناموفق:** `{blocked}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏁 عملیات به پایان رسید."
    )

    await status_msg.edit_text(report_text, parse_mode='Markdown')
    

    await update.message.reply_text(
        "منوی مدیریت:",
        reply_markup=get_admin_keyboard()
    )
    return ADMIN_MENU

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("لغو شد.", reply_markup=get_admin_keyboard())
    return ADMIN_MENU