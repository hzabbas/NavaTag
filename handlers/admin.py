import os
import sys
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import Config
from database.user_service import (
    get_total_users_count, 
    get_all_users_id, 
    add_locked_channel, 
    remove_locked_channel, 
    get_locked_channels,
    ban_user,
    unban_user,
    is_banned,
    get_user_report,
    get_advanced_global_stats,
    get_user_info,
    get_today_users
)

ADMIN_MENU, BROADCAST_REQUEST, WAITING_LOCK_CHANNEL, WAITING_USER_ID, WAITING_DIRECT_MESSAGE = range(5)


def get_admin_keyboard():
    locks = get_locked_channels()
    lock_status = f"{len(locks)} کانال" if locks else "❌ غیرفعال"
    keyboard = [
        [
            InlineKeyboardButton("📊 آمار پیشرفته", callback_data='admin_adv_stats'),
            InlineKeyboardButton("👤 مدیریت کاربران", callback_data='admin_search_user')
        ],
        [
            InlineKeyboardButton(f"🔒 قفل جوین ({lock_status})", callback_data='admin_lock_menu'),
            InlineKeyboardButton("📢 ارسال همگانی", callback_data='admin_broadcast')
        ],
        [
            InlineKeyboardButton("📥 بکاپ دیتابیس", callback_data='admin_backup'),
            InlineKeyboardButton("🧹 پاکسازی موقت", callback_data='admin_clean')
        ],
        [
            InlineKeyboardButton("🆕 کاربران امروز", callback_data='admin_today_users'),
            InlineKeyboardButton("🔄 ری‌استارت سیستم", callback_data='admin_restart')
        ],
        [
            InlineKeyboardButton("❌ خروج", callback_data='close_panel')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def escape_md(text):
    if not text:
        return ""
    return str(text).replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[')


async def show_user_profile(query, user_id):
    user_info = get_user_info(user_id)
    total_acts, recent_acts = get_user_report(user_id)
    banned = is_banned(user_id)
    status_text = "🔴 مسدود" if banned else "🟢 فعال"

    u_name = escape_md(user_info[0]) if user_info and user_info[0] else "ندارد"
    f_name = escape_md(user_info[1]) if user_info and user_info[1] else "ناشناس"
    j_date = user_info[2][:10] if user_info and user_info[2] else "نامشخص"
    
    history = ""
    if recent_acts:
        for act in recent_acts:
            safe_detail = escape_md(act[1][:25])
            history += f"▪️ {act[0]} : {safe_detail}\n"
    else:
        history = "بدون سابقه"

    profile_text = (
        "⚜️ **پرونده جامع کاربر** ⚜️\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 نام: {f_name}\n"
        f"🔗 یوزرنیم: @{u_name}\n"
        f"🆔 شناسه: `{user_id}`\n"
        f"📅 تاریخ عضویت: {j_date}\n"
        f"🛡 وضعیت: {status_text}\n"
        f"🗄 کل پردازش‌ها: {total_acts}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "آخرین فعالیت‌ها:\n"
        f"{history}"
    )
    
    btn = InlineKeyboardButton("✅ رفع مسدودی", callback_data=f"unban_{user_id}") if banned else InlineKeyboardButton("🚫 مسدود کردن", callback_data=f"ban_{user_id}")
    keyboard = [
        [btn, InlineKeyboardButton("✉️ ارسال پیام", callback_data=f"msguser_{user_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]
    ]
    
    await query.edit_message_text(text=profile_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return ADMIN_MENU


async def process_user_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_text = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    if not user_id_text.isdigit():
        msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="❌ فرمت نامعتبر! شناسه باید عددی باشد.")
        await asyncio.sleep(2)
        try:
            await msg.delete()
        except:
            pass
        return WAITING_USER_ID
        
    class DummyQuery:
        async def edit_message_text(self, text, reply_markup, parse_mode):
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode=parse_mode)
            
    return await show_user_profile(DummyQuery(), int(user_id_text))


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
    panel_text = (
        "⚡️ **پنل مدیریت پیشرفته و هوشمند نواتگ** ⚡️\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "به بخش کنترل مرکزی خوش آمدید.\n"
        "از طریق گزینه‌های زیر می‌توانید کنترل کامل ربات، مانیتورینگ منابع و مدیریت کاربران را به عهده بگیرید.\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    await update.message.reply_text(
        text=panel_text,
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
        panel_text = (
            "⚡️ **پنل مدیریت پیشرفته و هوشمند نواتگ** ⚡️\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "یکی از گزینه‌های زیر را جهت مدیریت انتخاب کنید:\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(
            text=panel_text,
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
    if data == 'admin_today_users':
        today_users = get_today_users()
        if not today_users:
            await query.answer("هیچ کاربری امروز اضافه نشده است.", show_alert=True)
            return ADMIN_MENU
        
        text = "🆕 **کاربران جدید امروز:**\n\n"
        for uid, fname, uname in today_users[:50]:
            safe_fname = escape_md(fname)
            safe_uname = escape_md(uname) if uname else 'ندارد'
            text += f"▪️ {safe_fname} (`{uid}`) - @{safe_uname}\n"
        
        await query.edit_message_text(
            text=text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]]),
            parse_mode='Markdown'
        )
        return ADMIN_MENU
    if data == 'admin_restart':
        await query.answer("⚡ در حال ری‌استارت آنی ربات...", show_alert=True)
        try:
            await query.message.delete()
        except:
            pass
        os.execl(sys.executable, sys.executable, *sys.argv)
    if data == 'admin_stats':
        count = get_total_users_count()
        try:
            folder_size = sum(os.path.getsize(os.path.join(Config.DOWNLOAD_PATH, f)) for f in os.listdir(Config.DOWNLOAD_PATH) if os.path.isfile(os.path.join(Config.DOWNLOAD_PATH, f)))
            folder_size_mb = folder_size / (1024 * 1024)
        except:
            folder_size_mb = 0
        try:
            load_avg = os.getloadavg()[0]
        except:
            load_avg = "N/A"
        await query.answer()
        stats_text = (
            "📊 **گزارش جامع وضعیت سرور و ربات**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 **تعداد کل کاربران:** `{count}`\n"
            f"📂 **حجم فایل‌های موقت:** `{folder_size_mb:.2f} MB`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 **میانگین بارگذاری سیستم (Load Avg):** `{load_avg}`\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⏱ وضعیت سیستم کاملاً پایدار است."
        )
        await query.edit_message_text(
             text=stats_text,
             reply_markup=get_admin_keyboard(),
             parse_mode='Markdown'
        )
        return ADMIN_MENU

    if data == 'admin_adv_stats':
        users_count = get_total_users_count()
        today_acts, total_acts = get_advanced_global_stats()
        stats_text = (
            "⚜️ **سیستم مانیتورینگ نواتگ** ⚜️\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 کل کاربران: {users_count}\n"
            f"📈 پردازش‌های امروز: {today_acts}\n"
            f"🗄 کل پردازش‌های سیستم: {total_acts}\n"
            "━━━━━━━━━━━━━━━━━━━━"
        )
        await query.edit_message_text(text=stats_text, reply_markup=get_admin_keyboard(), parse_mode='Markdown')
        return ADMIN_MENU

    if data == 'admin_search_user':
        await query.edit_message_text(
            "🔎 **جستجوی کاربر**\n\nلطفاً شناسه عددی کاربر را ارسال کنید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data='back_to_main')]]),
            parse_mode='Markdown'
        )
        return WAITING_USER_ID

    if data.startswith('ban_'):
        target_id = int(data.split('_')[1])
        ban_user(target_id)
        await query.answer("کاربر مسدود شد", show_alert=True)
        return await show_user_profile(query, target_id)

    if data.startswith('unban_'):
        target_id = int(data.split('_')[1])
        unban_user(target_id)
        await query.answer("محدودیت رفع شد", show_alert=True)
        return await show_user_profile(query, target_id)

    if data.startswith('msguser_'):
        target_id = int(data.split('_')[1])
        context.user_data['target_dm_id'] = target_id
        await query.edit_message_text(
            "✉️ **ارسال پیام مستقیم**\n\nلطفاً پیام خود را بفرستید تا از طرف ربات به کاربر ارسال شود:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data='back_to_main')]]),
            parse_mode='Markdown'
        )
        return WAITING_DIRECT_MESSAGE

    elif data == 'admin_broadcast':
        await query.answer()
        await query.edit_message_text(
            "📢 **پیام همگانی**\nپیامتان را بفرستید:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_main')]]),
            parse_mode='Markdown'
        )
        return BROADCAST_REQUEST
    elif data == 'admin_backup':
        await query.answer("ارسال دیتابیس...")
        if os.path.exists('bot_database.db'):
            await context.bot.send_document(user_id, open('bot_database.db', 'rb'), filename="backup.db")
        return ADMIN_MENU
    elif data == 'admin_clean':
        await query.answer("در حال پاکسازی...")
        folder = Config.DOWNLOAD_PATH
        try:
            for f in os.listdir(folder):
                os.unlink(os.path.join(folder, f))
        except:
            pass
        await query.answer("✅ پاکسازی شد.", show_alert=True)
        return await admin_callback(update, context)
    elif data == 'close_panel':
        await query.answer("بسته شد")
        await query.message.delete()
        return ConversationHandler.END


async def set_lock_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat_id = update.effective_chat.id
    try:
        await msg.delete()
    except:
        pass
    target_chat_id = None
    if msg.forward_origin:
        if msg.forward_origin.type == 'channel':
            target_chat_id = msg.forward_origin.chat.id
        else:
            temp = await context.bot.send_message(chat_id, "❌ این پیام از کانال نیست!")
            await asyncio.sleep(3)
            try:
                await temp.delete()
            except:
                pass
            return WAITING_LOCK_CHANNEL
    else:
        text = msg.text.strip()
        if text.startswith('@') or text.startswith('-100') or text.isdigit():
            target_chat_id = text
        else:
            temp = await context.bot.send_message(chat_id, "❌ آیدی نامعتبر! (باید با @ شروع شود یا فوروارد باشد)")
            await asyncio.sleep(3)
            try:
                await temp.delete()
            except:
                pass
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
            try:
                await context.bot.delete_message(chat_id, instruct_id)
            except:
                pass
            context.user_data['lock_instruction_msg_id'] = None
        safe_title = chat_info.title.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
        success = await context.bot.send_message(
            chat_id,
            f"✅ کانال **{safe_title}** به لیست قفل اضافه شد.",
            parse_mode='Markdown'
        )
        await asyncio.sleep(3)
        try:
            await success.delete()
        except:
            pass
        await admin_panel(update, context)
        return ADMIN_MENU
    except Exception as e:
        err_text = "❌ خطا: ربات در کانال ادمین نیست یا آیدی اشتباه است."
        if "Not found" in str(e):
            err_text = "❌ کانال پیدا نشد."
        temp = await context.bot.send_message(chat_id, err_text)
        await asyncio.sleep(4)
        try:
            await temp.delete()
        except:
            pass
        return WAITING_LOCK_CHANNEL


async def process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != Config.ADMIN_ID:
        return ConversationHandler.END
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


async def send_direct_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = context.user_data.get('target_dm_id')
    if not target_id:
        return ADMIN_MENU
    try:
        await update.message.copy(chat_id=target_id)
        await update.message.reply_text("✅ پیام با موفقیت ارسال شد.", reply_markup=get_admin_keyboard())
    except Exception:
        await update.message.reply_text("❌ ارسال پیام ناموفق بود (احتمالاً کاربر ربات را بلاک کرده است).", reply_markup=get_admin_keyboard())
    return ADMIN_MENU
