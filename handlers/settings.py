import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest

from database.user_service import (
    get_selected_channels, set_fast_mode, get_fast_mode, 
    set_user_preset, get_user_presets, delete_user_preset, 
    get_user_channels, toggle_channel_selection, delete_channel
)
from handlers.start import start

SETTINGS_MENU, WAITING_PRESET_VALUE, WAITING_SETTINGS_CHANNEL = range(3)

async def safe_delete(message):
    if not message:
        return
    try:
        await message.delete()
    except BadRequest:
        pass
    except Exception as e:
        print(f"Delete Error: {e}")

def get_settings_keyboard(user_id):
    is_fast = get_fast_mode(user_id)
    fast_icon = "✅ روشن" if is_fast else "❌ خاموش"
    
    presets = get_user_presets(user_id)
    selected_ch = get_selected_channels(user_id)
    ch_status = f"{len(selected_ch)} کانال" if selected_ch else "❌ غیرفعال"
    
    def tag_status(tag):
        if tag == 'cover':
            return "🔒 فیکس" if 'has_cover' in presets else "📝 تنظیم نشده"
        return f"🔒 {presets[tag]}" if tag in presets else "📝 تنظیم نشده"

    keyboard = [
        [InlineKeyboardButton(f"⚡️ حالت ویرایش سریع: {fast_icon}", callback_data='toggle_fast_mode')],
        [InlineKeyboardButton(f"📢 ارسال خودکار به کانال: {ch_status}", callback_data='manage_channels_settings')],
        [InlineKeyboardButton("🛠 تنظیمات تگ‌های ثابت (قفل) 🛠", callback_data='ignore')],
        [
            InlineKeyboardButton(f"👤 خواننده: {tag_status('artist')}", callback_data='set_preset_artist'),
            InlineKeyboardButton(f"🎵 آلبوم: {tag_status('album')}", callback_data='set_preset_album')
        ],
        [
            InlineKeyboardButton(f"🎹 ژانر: {tag_status('genre')}", callback_data='set_preset_genre'),
            InlineKeyboardButton(f"📅 سال: {tag_status('year')}", callback_data='set_preset_year')
        ],
        [
            InlineKeyboardButton(f"🖼 کاور ثابت: {tag_status('cover')}", callback_data='set_preset_cover'),
            InlineKeyboardButton(f"💬 کامنت: {tag_status('comment')}", callback_data='set_preset_comment')
        ],
        [InlineKeyboardButton("❌ بستن منوی تنظیمات", callback_data='close_settings')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def settings_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg_text = (
        "⚙️ **تنظیمات شخصی شما**\n\n"
        "در اینجا می‌توانید:\n"
        "1️⃣ **ویرایش سریع:** اگر روشن باشد، آهنگ بلافاصله با تگ‌های شما ادیت و ارسال می‌شود (بدون نمایش پنل).\n"
        "2️⃣ **تگ‌های ثابت:** مقادیری که همیشه روی آهنگ‌های شما تنظیم شوند (مثل نام خودتان به عنوان آرتیست)."
    )

    if update.callback_query:
        await update.callback_query.answer()
        try:
            msg = await update.callback_query.edit_message_text(
                text=msg_text,
                reply_markup=get_settings_keyboard(user_id),
                parse_mode='Markdown'
            )
            context.user_data['settings_panel_id'] = msg.message_id
        except BadRequest:
            pass
    else:
        await safe_delete(update.message)
        msg = await update.message.reply_text(
            text=msg_text,
            reply_markup=get_settings_keyboard(user_id),
            parse_mode='Markdown'
        )
        context.user_data['settings_panel_id'] = msg.message_id

    return SETTINGS_MENU

async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data == 'manage_channels_settings':
        await show_settings_channels(update, context, mode='view')
        return SETTINGS_MENU

    if data.startswith('toggle_ch_set_'):
        ch_id = data.replace('toggle_ch_set_', '')
        toggle_channel_selection(user_id, ch_id)
        await show_settings_channels(update, context, mode='view')
        return SETTINGS_MENU

    if data.startswith('del_ch_set_'):
        ch_id = data.replace('del_ch_set_', '')
        delete_channel(user_id, ch_id)
        await query.answer("🗑 کانال حذف شد.", show_alert=False)
        await show_settings_channels(update, context, mode='delete')
        return SETTINGS_MENU

    if data == 'mode_delete_settings':
        await show_settings_channels(update, context, mode='delete')
        return SETTINGS_MENU

    if data == 'mode_view_settings':
        await show_settings_channels(update, context, mode='view')
        return SETTINGS_MENU
        
    if data == 'add_new_channel_settings':
        await query.answer()
        context.user_data['from_settings'] = True
        msg_text = (
            "➕ **افزودن کانال جدید**\n\n"
            "لطفاً آیدی کانال را بفرستید (مثل `@Channel`) یا یک پیام از آن **فوروارد** کنید.\n\n"
            "⚠️ **نکته:** ربات باید در آن کانال **ادمین** باشد."
        )
        keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data='manage_channels_settings')]]
        
        await query.edit_message_text(
            text=msg_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return WAITING_SETTINGS_CHANNEL 

    if data == 'back_to_main_settings':
        await query.edit_message_text(
            "⚙️ **تنظیمات شخصی شما**",
            reply_markup=get_settings_keyboard(user_id),
            parse_mode='Markdown'
        )
        return SETTINGS_MENU
        
    if data == 'close_settings':
        await query.answer("بازگشت به منوی اصلی")
        await start(update, context, edit=True)
        context.user_data.pop('settings_panel_id', None)
        return ConversationHandler.END
    
    if data == 'ignore':
        await query.answer()
        return SETTINGS_MENU

    if data == 'toggle_fast_mode':
        current = get_fast_mode(user_id)
        set_fast_mode(user_id, not current)
        await query.answer(f"ویرایش سریع {'فعال' if not current else 'غیرفعال'} شد")
        try:
            await query.edit_message_reply_markup(reply_markup=get_settings_keyboard(user_id))
        except BadRequest:
            pass
        return SETTINGS_MENU

    if data.startswith('set_preset_'):
        tag = data.replace('set_preset_', '')
        context.user_data['target_preset'] = tag
        
        if tag == 'cover':
            msg_text = "🖼 لطفاً عکس کاور ثابت خود را بفرستید (یا لینک عکس)."
        else:
            current_val = get_user_presets(user_id).get(tag, 'تنظیم نشده')
            msg_text = (
                f"✍️ مقدار ثابت برای **{tag.upper()}** را بفرستید.\n\n"
                f"مقدار فعلی: `{current_val}`\n"
                f"❌ برای حذف قفل، کلمه `del` را بفرستید."
            )
  
        await query.edit_message_text(
            msg_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data='back_to_settings')]])
        )
        return WAITING_PRESET_VALUE
    
    if data == 'back_to_settings':
        await query.edit_message_text(
            "⚙️ **تنظیمات شخصی شما**",
            reply_markup=get_settings_keyboard(user_id),
            parse_mode='Markdown'
        )
        return SETTINGS_MENU

async def receive_preset_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tag = context.user_data.get('target_preset')
    chat_id = update.effective_chat.id
    
    await safe_delete(update.message)

    status_text = ""

    if update.message.text:
        text = update.message.text.strip()
        
        if text.lower() == 'del':
            delete_user_preset(user_id, tag if tag != 'cover' else 'has_cover')
            status_text = f"🗑 قفل تگ {tag} برداشته شد."
        elif tag == 'year':
            if not text.isdigit() or len(text) != 4:
                err = await context.bot.send_message(chat_id, "⚠️ خطا: سال باید فقط عدد و ۴ رقمی باشد (مثلاً 2024)")
                await asyncio.sleep(3)
                await safe_delete(err)
                return WAITING_PRESET_VALUE 
            else:
                set_user_preset(user_id, tag, text)
                status_text = f"✅ تگ {tag} روی `{text}` قفل شد."
        else:
            set_user_preset(user_id, tag, text)
            status_text = f"✅ تگ {tag} روی `{text}` قفل شد."

    elif update.message.photo and tag == 'cover':
        file_id = update.message.photo[-1].file_id
        set_user_preset(user_id, 'has_cover', file_id)
        status_text = "✅ عکس کاور ثابت ذخیره شد."

    panel_id = context.user_data.get('settings_panel_id')
    final_text = f"{status_text}\n\n⚙️ **تنظیمات شخصی شما**"
    
    if panel_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=panel_id,
                text=final_text,
                reply_markup=get_settings_keyboard(user_id),
                parse_mode='Markdown'
            )
        except BadRequest:
            pass
        except Exception:
            new_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=final_text,
                reply_markup=get_settings_keyboard(user_id),
                parse_mode='Markdown'
            )
            context.user_data['settings_panel_id'] = new_msg.message_id
    else:
        new_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=final_text,
            reply_markup=get_settings_keyboard(user_id),
            parse_mode='Markdown'
        )
        context.user_data['settings_panel_id'] = new_msg.message_id

    return SETTINGS_MENU

async def show_settings_channels(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='view'):
    user_id = update.effective_user.id
    channels = get_user_channels(user_id)
    query = update.callback_query
    
    keyboard = []
    
    for ch_id, title, is_selected in channels:
        if mode == 'view':
            status = "✅" if is_selected else "❌"
            text = f"{status} {title}"
            callback = f"toggle_ch_set_{ch_id}"
        else:
            text = f"🗑 حذف: {title}"
            callback = f"del_ch_set_{ch_id}"
            
        keyboard.append([InlineKeyboardButton(text, callback_data=callback)])

    controls = []
    if mode == 'view':
        controls.append(InlineKeyboardButton("➕ افزودن کانال", callback_data='add_new_channel_settings'))
        if channels:
            controls.append(InlineKeyboardButton("🗑 مدیریت حذف", callback_data='mode_delete_settings'))
    else:
        controls.append(InlineKeyboardButton("🔙 اتمام حذف", callback_data='mode_view_settings'))
    
    keyboard.append(controls)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data='back_to_main_settings')])
    
    msg_text = "📢 **مدیریت کانال‌های مقصد (تنظیمات)**\n\n✅ = ارسال می‌شود\n❌ = ارسال نمی‌شود"
    if mode == 'delete': msg_text = "⚠️ **حالت حذف:** برای حذف کانال روی آن کلیک کنید."

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if query.message.photo:
             await query.edit_message_caption(caption=msg_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
             await query.edit_message_text(text=msg_text, reply_markup=reply_markup, parse_mode='Markdown')
    except BadRequest:
        pass
    except Exception:
        await context.bot.send_message(user_id, msg_text, reply_markup=reply_markup, parse_mode='Markdown')