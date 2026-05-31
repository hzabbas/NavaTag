import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.error import BadRequest
from utils.locales import get_text
from utils.task_manager import with_task_protection

from database.user_service import (
    get_selected_channels, set_fast_mode, get_fast_mode, 
    set_user_preset, get_user_presets, delete_user_preset, 
    get_user_channels, toggle_channel_selection, delete_channel,
    get_user_language
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
    except Exception:
        pass

def get_settings_keyboard(user_id):
    is_fast = get_fast_mode(user_id)
    fast_icon = get_text(user_id, 'fast_mode_on') if is_fast else get_text(user_id, 'fast_mode_off')
    
    presets = get_user_presets(user_id)
    selected_ch = get_selected_channels(user_id)
    ch_status = get_text(user_id, 'active_channels').format(count=len(selected_ch)) if selected_ch else get_text(user_id, 'inactive')
    
    def tag_status(tag):
        if tag == 'cover':
            return get_text(user_id, 'fixed_cover') if 'has_cover' in presets else get_text(user_id, 'not_set')
        return get_text(user_id, 'locked').format(value=presets[tag]) if tag in presets else get_text(user_id, 'not_set')

    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'fast_mode_btn').format(status=fast_icon), callback_data='toggle_fast_mode')],
        [InlineKeyboardButton(get_text(user_id, 'auto_send_btn').format(status=ch_status), callback_data='manage_channels_settings')],
        [InlineKeyboardButton(get_text(user_id, 'fixed_tags_btn'), callback_data='ignore')],
        [
            InlineKeyboardButton(get_text(user_id, 'artist_btn').format(status=tag_status('artist')), callback_data='set_preset_artist'),
            InlineKeyboardButton(get_text(user_id, 'album_btn').format(status=tag_status('album')), callback_data='set_preset_album')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'genre_btn').format(status=tag_status('genre')), callback_data='set_preset_genre'),
            InlineKeyboardButton(get_text(user_id, 'year_btn').format(status=tag_status('year')), callback_data='set_preset_year')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'cover_btn').format(status=tag_status('cover')), callback_data='set_preset_cover'),
            InlineKeyboardButton(get_text(user_id, 'comment_btn').format(status=tag_status('comment')), callback_data='set_preset_comment')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'language_btn'), callback_data='toggle_language')
        ],
        [InlineKeyboardButton(get_text(user_id, 'close_settings_btn'), callback_data='close_settings')]
    ]
    return InlineKeyboardMarkup(keyboard)

@with_task_protection("action")
async def settings_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg_text = get_text(user_id, 'settings_menu')

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

@with_task_protection("action")
async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data == 'toggle_language':
        from database.user_service import set_user_setting
        current_lang = get_user_language(user_id)
        new_lang = 'en' if current_lang == 'fa' else 'fa'
        set_user_setting(user_id, 'language', new_lang)
        await query.answer(get_text(user_id, 'lang_changed'))
        try:
            await query.edit_message_text(
                text=get_text(user_id, 'settings_menu'),
                reply_markup=get_settings_keyboard(user_id),
                parse_mode='Markdown'
            )
        except BadRequest:
            pass
        return SETTINGS_MENU

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
        await query.answer(get_text(user_id, 'channel_deleted'), show_alert=False)
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
        msg_text = get_text(user_id, 'add_channel_prompt')
        keyboard = [[InlineKeyboardButton(get_text(user_id, 'btn_back'), callback_data='manage_channels_settings')]]
        
        await query.edit_message_text(
            text=msg_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return WAITING_SETTINGS_CHANNEL 

    if data == 'back_to_main_settings':
        await query.edit_message_text(
            get_text(user_id, 'settings_menu'),
            reply_markup=get_settings_keyboard(user_id),
            parse_mode='Markdown'
        )
        return SETTINGS_MENU
        
    if data == 'close_settings':
        await query.answer()
        await start(update, context, edit=True)
        context.user_data.pop('settings_panel_id', None)
        return ConversationHandler.END
    
    if data == 'ignore':
        await query.answer()
        return SETTINGS_MENU

    if data == 'toggle_fast_mode':
        current = get_fast_mode(user_id)
        set_fast_mode(user_id, not current)
        
        lang = get_user_language(user_id)
        status_fa = 'فعال' if not current else 'غیرفعال'
        status_en = 'enabled' if not current else 'disabled'
        msg = f"ویرایش سریع {status_fa} شد" if lang == 'fa' else f"Fast mode {status_en}"
        
        await query.answer(msg)
        try:
            await query.edit_message_reply_markup(reply_markup=get_settings_keyboard(user_id))
        except BadRequest:
            pass
        return SETTINGS_MENU

    if data.startswith('set_preset_'):
        tag = data.replace('set_preset_', '')
        context.user_data['target_preset'] = tag
        
        if tag == 'cover':
            msg_text = get_text(user_id, 'send_cover')
        else:
            current_val = get_user_presets(user_id).get(tag, '-')
            msg_text = f"✍️ {tag.upper()} \n\n`{current_val}`\n❌ 'del'"
  
        await query.edit_message_text(
            msg_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'btn_back'), callback_data='back_to_settings')]])
        )
        return WAITING_PRESET_VALUE
    
    if data == 'back_to_settings':
        await query.edit_message_text(
            get_text(user_id, 'settings_menu'),
            reply_markup=get_settings_keyboard(user_id),
            parse_mode='Markdown'
        )
        return SETTINGS_MENU

@with_task_protection("action")
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
            status_text = f"🗑 {tag}"
        elif tag == 'year':
            if not text.isdigit() or len(text) != 4:
                err = await context.bot.send_message(chat_id, "⚠️")
                await asyncio.sleep(3)
                await safe_delete(err)
                return WAITING_PRESET_VALUE 
            else:
                set_user_preset(user_id, tag, text)
                status_text = f"✅ {tag} `{text}`"
        else:
            set_user_preset(user_id, tag, text)
            status_text = f"✅ {tag} `{text}`"

    elif update.message.photo and tag == 'cover':
        file_id = update.message.photo[-1].file_id
        set_user_preset(user_id, 'has_cover', file_id)
        status_text = "✅"

    panel_id = context.user_data.get('settings_panel_id')
    final_text = f"{status_text}\n\n⚙️"
    
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
            text = f"🗑: {title}"
            callback = f"del_ch_set_{ch_id}"
            
        keyboard.append([InlineKeyboardButton(text, callback_data=callback)])

    controls = []
    if mode == 'view':
        controls.append(InlineKeyboardButton("➕", callback_data='add_new_channel_settings'))
        if channels:
            controls.append(InlineKeyboardButton("🗑", callback_data='mode_delete_settings'))
    else:
        controls.append(InlineKeyboardButton(get_text(user_id, 'btn_back'), callback_data='mode_view_settings'))
    
    keyboard.append(controls)
    keyboard.append([InlineKeyboardButton(get_text(user_id, 'btn_back'), callback_data='back_to_main_settings')])
    
    msg_text = get_text(user_id, 'settings_menu')
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
