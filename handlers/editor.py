import os
import asyncio
import random
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, 
    InputMediaPhoto, InlineQueryResultCachedAudio, 
    InlineQueryResultCachedVoice, InlineQueryResultCachedDocument
)
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest
from pydub import AudioSegment
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

from config import Config
from database.user_service import (
    add_channel, get_user_channels, toggle_channel_selection, 
    delete_channel, get_selected_channels, get_user_presets, get_fast_mode
)
from utils.states import SELECT_ACTION, WAITING_INPUT, WAITING_COVER, WAITING_CHANNEL
from utils.tagger import get_tags, set_tag, set_cover_from_file, delete_all_tags, apply_tags
from utils.pro_tools import convert_audio, detect_lyrics_lang, generate_standard_filename, smart_clean_tags
from utils.locales import get_text

async def safe_delete(message):
    if not message:
        return
    try:
        await message.delete()
    except BadRequest:
        pass
    except Exception as e:
        print(f"Delete Error: {e}")

def cleanup_all_files(file_path):
    if not file_path:
        return
    
    base_path = os.path.splitext(file_path)[0]
    extensions = ['.mp3', '.ogg', '.wav', '.flac', '.jpg', '.png']
    
    for ext in extensions:
        target = base_path + ext
        try:
            if os.path.exists(target):
                os.remove(target)
        except OSError as e:
            print(f"Cleanup Error ({target}): {e}")
            


async def start_editor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text(get_text(user_id, 'downloading'))
    
    file_id = update.message.audio.file_id
    new_file = await context.bot.get_file(file_id)
    file_path = os.path.join(Config.DOWNLOAD_PATH, f"{update.message.audio.file_unique_id}.mp3")
    await new_file.download_to_drive(file_path)

    context.user_data['file_path'] = file_path
    context.user_data['changes'] = []
    context.user_data['filename'] = update.message.audio.file_name or "music.mp3"
    context.user_data['locked_tags'] = []

    presets = get_user_presets(user_id)
    if presets:
        cover_file_id = presets.get('has_cover')
        tags_to_apply = {k: v for k, v in presets.items() if k != 'has_cover'}
        
        if tags_to_apply:
            apply_tags(file_path, tags_to_apply)
            for t in tags_to_apply: context.user_data['changes'].append(t)
        
        if cover_file_id:
            try:
                cover_file = await context.bot.get_file(cover_file_id)
                cover_path = os.path.join(Config.DOWNLOAD_PATH, f"preset_cover_{user_id}.jpg")
                await cover_file.download_to_drive(cover_path)
                set_cover_from_file(file_path, cover_path)
                os.remove(cover_path) 
                context.user_data['changes'].append('has_cover')
            except Exception as e:
                print(f"Error setting preset cover: {e}")

    await safe_delete(msg)

    if get_fast_mode(user_id):
        await fast_finish_process(update, context)
        return ConversationHandler.END

    await show_panel(update, context, is_first_time=True)
    return SELECT_ACTION

async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, is_first_time=False):
    file_path = context.user_data.get('file_path')
    if not file_path:
        return

    panel_id = context.user_data.get('panel_id')
    changes = context.user_data.get('changes', [])
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    tags = get_tags(file_path)

    def mark(tag_name): return "✏️" if tag_name in changes else ""
    
    lyrics_stat = get_text(user_id, 'has_it') if tags.get('lyrics') else get_text(user_id, 'doesnt_have_it')
    cover_stat = get_text(user_id, 'has_it') if tags.get('has_cover') else get_text(user_id, 'doesnt_have_it')

    caption = get_text(user_id, 'editor_panel').format(
        size=tags['size'], duration=tags['duration'], artist=tags['artist'], mark_artist=mark('artist'),
        title=tags['title'], mark_title=mark('title'), album=tags['album'], mark_album=mark('album'),
        genre=tags['genre'], mark_genre=mark('genre'), year=tags['year'], mark_year=mark('year'),
        track=tags.get('track', '0'), mark_track=mark('track'), comment=tags.get('comment', ''),
        mark_comment=mark('comment'), lyrics_status=lyrics_stat, mark_lyrics=mark('lyrics'),
        cover_status=cover_stat, mark_cover=mark('has_cover')
    )

    keyboard = [
        [InlineKeyboardButton(get_text(user_id, 'btn_title'), callback_data='edit_title'), InlineKeyboardButton(get_text(user_id, 'btn_artist'), callback_data='edit_artist')],
        [InlineKeyboardButton(get_text(user_id, 'btn_genre'), callback_data='edit_genre'), InlineKeyboardButton(get_text(user_id, 'btn_album'), callback_data='edit_album')],
        [InlineKeyboardButton(get_text(user_id, 'btn_track'), callback_data='edit_track'), InlineKeyboardButton(get_text(user_id, 'btn_year'), callback_data='edit_year')],
        [InlineKeyboardButton(get_text(user_id, 'btn_comment'), callback_data='edit_comment'), InlineKeyboardButton(get_text(user_id, 'btn_lyrics'), callback_data='edit_lyrics')],
        [InlineKeyboardButton(get_text(user_id, 'btn_cover'), callback_data='edit_cover'), InlineKeyboardButton(get_text(user_id, 'btn_advanced'), callback_data='goto_advanced')],
        [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel'), InlineKeyboardButton(get_text(user_id, 'btn_done'), callback_data='done')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    real_thumb_path = get_thumb_path(file_path)
    default_thumb_path = "default.jpg"
    final_photo_path = real_thumb_path if real_thumb_path else default_thumb_path
    
    is_url = False
    if not os.path.exists(final_photo_path):
        final_photo_path = "https://i.pinimg.com/736x/26/c1/68/26c168251a466a5dde45a7206719d8a2.jpg"
        is_url = True

    try:
        if is_first_time:
            if is_url:
                msg = await context.bot.send_photo(chat_id, photo=final_photo_path, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                with open(final_photo_path, 'rb') as f:
                    msg = await context.bot.send_photo(chat_id, photo=f, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
            context.user_data['panel_id'] = msg.message_id
        else:
            try:
                if is_url:
                    media = InputMediaPhoto(media=final_photo_path, caption=caption, parse_mode='Markdown')
                    await context.bot.edit_message_media(chat_id=chat_id, message_id=panel_id, media=media, reply_markup=reply_markup)
                else:
                    with open(final_photo_path, 'rb') as f:
                        media = InputMediaPhoto(media=f, caption=caption, parse_mode='Markdown')
                        await context.bot.edit_message_media(chat_id=chat_id, message_id=panel_id, media=media, reply_markup=reply_markup)
            except Exception:
                try: await context.bot.delete_message(chat_id, panel_id)
                except: pass
                
                if is_url:
                    msg = await context.bot.send_photo(chat_id, photo=final_photo_path, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
                else:
                    with open(final_photo_path, 'rb') as f:
                        msg = await context.bot.send_photo(chat_id, photo=f, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
                context.user_data['panel_id'] = msg.message_id

    except Exception as e:
        print(f"Panel Error: {e}")
    finally:
        if real_thumb_path and os.path.exists(real_thumb_path):
            try: os.remove(real_thumb_path)
            except: pass

async def show_advanced_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    panel_id = context.user_data.get('panel_id')
    current_filename = context.user_data.get('filename')
    user_id = update.effective_user.id
    
    caption = get_text(user_id, 'advanced_panel').format(filename=current_filename)

    keyboard = [
        [
            InlineKeyboardButton(get_text(user_id, 'btn_convert'), callback_data='menu_convert'),
            InlineKeyboardButton(get_text(user_id, 'btn_clean'), callback_data='pro_clean')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'btn_cut'), callback_data='start_cut'),
            InlineKeyboardButton(get_text(user_id, 'btn_rename'), callback_data='auto_rename')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'btn_lock'), callback_data='menu_lock'),
            InlineKeyboardButton(get_text(user_id, 'btn_lang'), callback_data='detect_lang')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'btn_edit_filename'), callback_data='edit_filename'),
            InlineKeyboardButton(get_text(user_id, 'btn_channels'), callback_data='manage_channels')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'btn_voice'), callback_data='convert_to_voice')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'btn_back'), callback_data='goto_main')
        ]
    ]
    
    try:
        await context.bot.edit_message_caption(
            chat_id=update.effective_chat.id,
            message_id=panel_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        print(f"Advanced Panel Error: {e}")


async def show_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, mode='view'):
    user_id = update.effective_user.id
    channels = get_user_channels(user_id)
    chat_id = update.effective_chat.id
    
    keyboard = []
    
    for ch_id, title, is_selected in channels:
        if mode == 'view':
            status = "✅" if is_selected else "❌"
            text = f"{status} {title}"
            callback = f"toggle_ch_{ch_id}"
        else:
            text = f"🗑 حذف: {title}"
            callback = f"del_ch_{ch_id}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback)])

    controls = []
    if mode == 'view':
        controls.append(InlineKeyboardButton("➕ افزودن کانال", callback_data='add_new_channel'))
        if channels:
            controls.append(InlineKeyboardButton("🗑 مدیریت حذف", callback_data='mode_delete'))
    else:
        controls.append(InlineKeyboardButton("🔙 اتمام حذف", callback_data='mode_view'))
    
    keyboard.append(controls)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل پیشرفته", callback_data='goto_advanced')])

    msg_text = "📢 **مدیریت کانال‌های مقصد**\n\n✅ = ارسال می‌شود\n❌ = ارسال نمی‌شود"
    if mode == 'delete': msg_text = "⚠️ **حالت حذف:** برای حذف کانال روی آن کلیک کنید."

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        message = update.callback_query.message
        try:
            if message.photo:
                await update.callback_query.edit_message_caption(
                    caption=msg_text, 
                    reply_markup=reply_markup, 
                    parse_mode='Markdown'
                )
            else:
                await update.callback_query.edit_message_text(
                    text=msg_text, 
                    reply_markup=reply_markup, 
                    parse_mode='Markdown'
                )
        except Exception:
            try: await message.delete()
            except: pass
            msg = await context.bot.send_message(chat_id, msg_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        
        await context.bot.send_message(chat_id, msg_text, reply_markup=reply_markup, parse_mode='Markdown')


async def handle_button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"🔘 Button Clicked: {update.callback_query.data}")
    query = update.callback_query
    data = query.data
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    file_path = context.user_data.get('file_path')

    if not file_path and data not in ['goto_main', 'cancel']:
        await query.answer(get_text(user_id, 'bot_reset'), show_alert=True)
        return ConversationHandler.END

    if data == 'goto_advanced':
        msg_id = context.user_data.get('msg_to_delete')
        if msg_id:
            try: await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except: pass
            context.user_data['msg_to_delete'] = None
            
        await show_advanced_panel(update, context)
        return SELECT_ACTION 

    if data == 'goto_main':
        await show_panel(update, context, is_first_time=False)
        return SELECT_ACTION 

    if data == 'cancel': 
        await query.answer(get_text(user_id, 'op_cancelled'))
        await query.message.delete()
        if file_path and os.path.exists(file_path): 
            try: os.remove(file_path)
            except: pass
        return ConversationHandler.END

    if data == 'done': 
        await finish_process(update, context)
        return ConversationHandler.END

    if data == 'manage_channels': 
        await show_channels_menu(update, context, mode='view')
        return SELECT_ACTION

    if data == 'mode_delete':
        await show_channels_menu(update, context, mode='delete')
        return SELECT_ACTION
    if data == 'mode_view':
        await show_channels_menu(update, context, mode='view')
        return SELECT_ACTION

    if data == 'add_new_channel':
        await query.answer()
        keyboard = [[InlineKeyboardButton(get_text(user_id, 'btn_back'), callback_data='mode_view')]] 
        msg = await query.message.reply_text(
            get_text(user_id, 'add_channel_prompt'),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        context.user_data['msg_to_delete'] = msg.message_id
        return WAITING_CHANNEL

    if data.startswith('toggle_ch_'):
        ch_id = data.replace('toggle_ch_', '')
        toggle_channel_selection(user_id, ch_id)
        await show_channels_menu(update, context, mode='view') 
        return SELECT_ACTION

    if data.startswith('del_ch_'):
        ch_id = data.replace('del_ch_', '')
        delete_channel(user_id, ch_id)
        await query.answer(get_text(user_id, 'channel_deleted'), show_alert=False)
        await show_channels_menu(update, context, mode='delete') 
        return SELECT_ACTION

    if data == 'start_cut':
        await query.answer()
        msg = await query.message.reply_text(
            get_text(user_id, 'cutter_prompt'),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text(user_id, 'btn_back'), callback_data='goto_advanced')]])
        )
        context.user_data['msg_to_delete'] = msg.message_id
        context.user_data['current_tag'] = 'cut_audio'
        return WAITING_INPUT

    if data == 'menu_convert': await show_convert_menu(update, context); return SELECT_ACTION
    if data == 'menu_lock': await show_lock_menu(update, context); return SELECT_ACTION

    if data == 'convert_to_voice':
        await query.answer(get_text(user_id, 'converting_voice'))
        current_path = context.user_data.get('file_path')
        
        voice_path = await asyncio.to_thread(convert_audio, current_path, "ogg", "64k")
        
        if voice_path:
            if current_path != voice_path and os.path.exists(current_path):
                try: os.remove(current_path)
                except OSError: pass
            
            context.user_data['file_path'] = voice_path
            context.user_data['is_voice'] = True
            
            with open(voice_path, 'rb') as f:
                await query.message.reply_voice(
                    voice=f,
                    caption=get_text(user_id, 'voice_done')
                )
            
            await show_advanced_panel(update, context)
        else:
            await query.answer(get_text(user_id, 'convert_error'), show_alert=True)
            
        return SELECT_ACTION

    if data.startswith('convert_'):
        await query.answer(get_text(user_id, 'converting_format'))
        target = data.replace('convert_', '')
        
        fmt = 'mp3'
        bitrate = '320k'
        if target == 'mp3_128': bitrate = '128k'
        elif target == 'flac': fmt = 'flac'
        elif target == 'wav': fmt = 'wav' 
        elif target == 'ogg': fmt = 'ogg'; bitrate = '128k'

        old_tags = await asyncio.to_thread(get_tags, file_path) 
        new_path = await asyncio.to_thread(convert_audio, file_path, fmt, bitrate)
        
        if new_path:
            if os.path.exists(file_path) and file_path != new_path:
                try: os.remove(file_path)
                except OSError: pass
            
            if fmt != 'wav':
                await asyncio.to_thread(apply_tags, new_path, old_tags)
            
            context.user_data['file_path'] = new_path
            
            old_name = context.user_data.get('filename', 'music.mp3')
            base_name = os.path.splitext(old_name)[0]
            context.user_data['filename'] = f"{base_name}.{fmt}"
            
            await query.answer(get_text(user_id, 'format_done').format(fmt=fmt.upper()), show_alert=True)
            await show_advanced_panel(update, context)
        else:
            await query.answer(get_text(user_id, 'convert_error'), show_alert=True)
            
        return SELECT_ACTION

    if data == 'pro_clean':
        locks = context.user_data.get('locked_tags', [])
        success = await asyncio.to_thread(smart_clean_tags, file_path, locks)
        if success:
            await query.answer(get_text(user_id, 'file_cleaned'), show_alert=True)
        else:
            await query.answer(get_text(user_id, 'clean_error'), show_alert=True)
        context.user_data['changes'] = []
        await show_panel(update, context, is_first_time=False)
        return SELECT_ACTION

    if data.startswith('toggle_lock_'):
        tag = data.replace('toggle_lock_', '')
        locks = context.user_data.get('locked_tags', [])
        if tag in locks: locks.remove(tag)
        else: locks.append(tag)
        context.user_data['locked_tags'] = locks
        await show_lock_menu(update, context)
        return SELECT_ACTION

    if data == 'auto_rename':
        tags = await asyncio.to_thread(get_tags, file_path)
        new_name = generate_standard_filename(tags)
        context.user_data['filename'] = new_name
        await query.answer(get_text(user_id, 'new_name').format(name=new_name), show_alert=True)
        await show_advanced_panel(update, context)
        return SELECT_ACTION

    if data == 'detect_lang':
        tags = await asyncio.to_thread(get_tags, file_path)
        lang = await asyncio.to_thread(detect_lyrics_lang, tags.get('lyrics'))
        await query.answer(get_text(user_id, 'detected_lang').format(lang=lang), show_alert=True)
        return SELECT_ACTION

    tag_map = {
        'edit_title': 'title', 'edit_artist': 'artist', 'edit_album': 'album',
        'edit_genre': 'genre', 'edit_year': 'year', 'edit_track': 'track',
        'edit_comment': 'comment', 'edit_lyrics': 'lyrics', 'edit_filename': 'filename'
    }
    
    if data in tag_map:
        context.user_data['current_tag'] = tag_map[data]
        await query.answer(get_text(user_id, 'send_new_value'), show_alert=False)
        return WAITING_INPUT

    if data == 'edit_cover':
        await query.answer(get_text(user_id, 'send_cover'), show_alert=False)
        return WAITING_COVER

    return SELECT_ACTION

def _process_cut(path, start_ms, end_ms):
    audio = AudioSegment.from_file(path)
    if end_ms > len(audio) or start_ms >= end_ms:
        raise ValueError("Invalid range")
    cut_part = audio[start_ms:end_ms]
    cut_part.export(path, format="mp3")

async def receive_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_text = update.message.text.strip()
    tag_to_edit = context.user_data.get('current_tag')
    file_path = context.user_data.get('file_path')

    try: await update.message.delete()
    except: pass


    current_tag = context.user_data.get('current_tag')
    text = update.message.text.strip()

    if current_tag == 'cut_audio':
        old_msg_id = context.user_data.get('msg_to_delete')
        if old_msg_id:
            try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old_msg_id)
            except BadRequest: pass

        try: await update.message.delete()
        except BadRequest: pass

        try:
            start_str, end_str = text.split('-')
            def get_ms(time_str):
                m, s = map(int, time_str.split(':'))
                return (m * 60 + s) * 1000

            start_ms = get_ms(start_str)
            end_ms = get_ms(end_str)

            file_path = context.user_data.get('file_path')
            
            status_msg = await update.message.reply_text("⏳ در حال برش...")
            
            await asyncio.to_thread(_process_cut, file_path, start_ms, end_ms)

            await safe_delete(status_msg)
            temp_ok = await update.message.reply_text("✅ برش با موفقیت انجام شد!")
            
            await asyncio.sleep(2)
            await safe_delete(temp_ok)

            await show_advanced_panel(update, context)
            return SELECT_ACTION

        except Exception:
            err = await update.message.reply_text("❌ خطا در فرمت یا بازه نامعتبر! دوباره تلاش کنید.")
            context.user_data['msg_to_delete'] = err.message_id
            return WAITING_INPUT     
    if tag_to_edit == 'filename':
        if not new_text.lower().endswith(".mp3"): new_text += ".mp3"
        context.user_data['filename'] = new_text
        msg = await update.message.reply_text(f"✅ نام فایل شد: {new_text}")
        await asyncio.sleep(2)
        await safe_delete(msg)
        await show_advanced_panel(update, context)
        return SELECT_ACTION

    error_msg = None
    if tag_to_edit == 'year':
        if not new_text.isdigit() or len(new_text) != 4: error_msg = "❌ سال باید ۴ رقمی باشد."
    elif tag_to_edit == 'track':
        if not new_text.isdigit(): error_msg = "❌ شماره ترک باید عدد باشد."

    if error_msg:
        formatted_error = (
            f"⚠️ **اشتباه در ورود اطلاعات**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{error_msg}\n"
            f"♻️ لطفاً مجدداً مقدار صحیح را ارسال کنید."
        )
        msg = await update.message.reply_text(formatted_error, parse_mode='Markdown')
        await asyncio.sleep(4)
        await safe_delete(msg)
        return WAITING_INPUT

    success = set_tag(file_path, tag_to_edit, new_text)

    if success:
        if tag_to_edit not in context.user_data['changes']:
            context.user_data['changes'].append(tag_to_edit)
        await show_panel(update, context)
    else:
        msg = await update.message.reply_text("❌ خطا در ویرایش.")
        await asyncio.sleep(3)
        await safe_delete(msg)

    return SELECT_ACTION

async def receive_cover(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo: return WAITING_COVER
    try: await update.message.delete()
    except: pass

    photo_file = await update.message.photo[-1].get_file()
    cover_path = os.path.join(Config.DOWNLOAD_PATH, f"cover_{update.message.id}.jpg")
    await photo_file.download_to_drive(cover_path)
    file_path = context.user_data.get('file_path')
    
    success = set_cover_from_file(file_path, cover_path)
    if os.path.exists(cover_path): os.remove(cover_path)

    if success:
        if 'has_cover' not in context.user_data['changes']:
            context.user_data['changes'].append('has_cover')
        await show_panel(update, context)
        msg = await update.message.reply_text("✅ کاور تغییر کرد!")
        await asyncio.sleep(3)
        await safe_delete(msg)

    return SELECT_ACTION

async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = None
    channel_title = "Unknown Channel"


    if update.message.forward_origin and update.message.forward_origin.type == 'channel':
        channel_id = update.message.forward_origin.chat.id
        channel_title = update.message.forward_origin.chat.title
    elif update.message.text:
        channel_id = update.message.text.strip()

    try: await update.message.delete()
    except: pass


    msg_id = context.user_data.get('msg_to_delete')
    if msg_id:
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except: pass
        context.user_data['msg_to_delete'] = None

    try:
        bot_id = context.bot.id
        try:
            member = await context.bot.get_chat_member(chat_id=channel_id, user_id=bot_id)
        except Exception:
            raise Exception("ربات در این کانال عضو نیست یا آیدی اشتباه است.")

        if member.status not in ['administrator', 'creator']:
            raise Exception("⛔️ ربات در این کانال **ادمین** نیست!\nلطفاً ابتدا ربات را در کانال ادمین کنید.")
        
        if member.status == 'administrator' and not member.can_post_messages:
             raise Exception("⛔️ ربات ادمین است اما دسترسی **ارسال پیام** ندارد.")


        chat_info = await context.bot.get_chat(chat_id=channel_id)
        final_id = chat_info.id
        final_title = chat_info.title
        
        safe_title = final_title.replace('*', '').replace('_', '').replace('`', '').replace('[', '').replace(']', '')
        if add_channel(update.effective_user.id, final_id, final_title):
            success_text = f"✅ کانال **{safe_title}** اضافه شد!"
        else:
            success_text = "⚠️ این کانال قبلاً در لیست شما وجود دارد."


        if context.user_data.get('from_settings'):
            from handlers.settings import SETTINGS_MENU 
            
            msg = await context.bot.send_message(update.effective_chat.id, success_text, parse_mode='Markdown')
            await asyncio.sleep(2)
            await safe_delete(msg)
            
            context.user_data.pop('from_settings', None)
            
            user_id = update.effective_user.id
            panel_id = context.user_data.get('settings_panel_id')
            
            channels = get_user_channels(user_id)
            keyboard = []
            
            for ch_id, title, is_selected in channels:
                status = "✅" if is_selected else "❌"
                keyboard.append([InlineKeyboardButton(f"{status} {title}", callback_data=f"toggle_ch_set_{ch_id}")])
            
            controls = []
            controls.append(InlineKeyboardButton("➕ افزودن کانال", callback_data='add_new_channel_settings'))
            
            if channels: 
                controls.append(InlineKeyboardButton("🗑 مدیریت حذف", callback_data='mode_delete_settings'))
            
            keyboard.append(controls)
            keyboard.append([InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data='back_to_main_settings')])
            
            msg_text = "📢 **مدیریت کانال‌های مقصد (تنظیمات)**\n\n✅ = ارسال می‌شود\n❌ = ارسال نمی‌شود"

            if panel_id:
                try:
                    await context.bot.edit_message_text(
                        chat_id=user_id,
                        message_id=panel_id,
                        text=msg_text,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode='Markdown'
                    )
                except BadRequest:
                    pass
                except Exception:
                    new_msg = await context.bot.send_message(user_id, msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
                    context.user_data['settings_panel_id'] = new_msg.message_id
            
            return SETTINGS_MENU

        else:
            msg = await update.message.reply_text(success_text, parse_mode='Markdown')
            await asyncio.sleep(2)
            await safe_delete(msg)

            await show_advanced_panel(update, context) 
            return SELECT_ACTION

    except Exception as e:     
        err_msg = await update.message.reply_text(f"❌ {e}")
        await asyncio.sleep(4)
        await safe_delete(err_msg)
        
        if context.user_data.get('from_settings'):
            from handlers.settings import WAITING_SETTINGS_CHANNEL
            return WAITING_SETTINGS_CHANNEL
            
        return WAITING_CHANNEL

async def finish_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer(get_text(user_id, 'uploading'))
    
    file_path = context.user_data.get('file_path')
    is_voice = context.user_data.get('is_voice', False)
    display_filename = context.user_data.get('filename', 'music.mp3')

    selected_channels = get_selected_channels(user_id)
    tags = get_tags(file_path)
    
    report_text = get_text(user_id, 'report_header').format(
        filename=display_filename,
        size=tags['size'],
        duration=tags['duration']
    )

    thumb_path = None
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC
        audio_tags = MP3(file_path, ID3=ID3)
        if audio_tags.tags:
            for tag in audio_tags.tags.values():
                if isinstance(tag, APIC):
                    thumb_path = file_path.replace(os.path.splitext(file_path)[1], ".jpg")
                    with open(thumb_path, "wb") as f: f.write(tag.data)
                    break
    except: pass

    sent_audio = None
    sent_count = 0

    try:
        with open(file_path, 'rb') as audio_file:
            thumb_file = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
            
            if is_voice:
                sent_audio = await query.message.reply_voice(
                    voice=audio_file,
                    caption=get_text(user_id, 'voice_caption')
                )
                if selected_channels:
                    for ch_id in selected_channels:
                        try:
                            audio_file.seek(0)
                            await context.bot.send_voice(chat_id=ch_id, voice=audio_file)
                            sent_count += 1
                        except: pass
            else:
                sent_audio = await query.message.reply_audio(
                    audio=audio_file,
                    filename=display_filename,
                    caption=get_text(user_id, 'audio_caption'),
                    thumbnail=thumb_file,
                    parse_mode='Markdown'
                )
                if selected_channels:
                    for ch_id in selected_channels:
                        try:
                            audio_file.seek(0)
                            if thumb_file: thumb_file.seek(0)
                            await context.bot.send_audio(
                                chat_id=ch_id,
                                audio=audio_file,
                                filename=display_filename,
                                thumbnail=thumb_file
                            )
                            sent_count += 1
                        except: pass
            
            if thumb_file: thumb_file.close()
    except Exception as e:
        print(f"Send Error: {e}")

    keyboard = []
    if sent_audio:
        file_id = None
        query_data = "" 

        if is_voice:
            file_id = sent_audio.voice.file_id
            query_data = f"voice:{file_id}"
        else:
            file_id = sent_audio.audio.file_id
            if file_path.lower().endswith(".mp3"):
                query_data = f"audio:{file_id}"
            else:
                query_data = f"{file_id}"

        keyboard.append([InlineKeyboardButton(get_text(user_id, 'share_btn'), switch_inline_query=query_data)])
        
    if selected_channels:
        report_text += get_text(user_id, 'sent_to_channels').format(count=sent_count)

    report_text += get_text(user_id, 'thanks')

    await query.message.reply_text(
        report_text, 
        reply_markup=InlineKeyboardMarkup(keyboard), 
        parse_mode='Markdown'
    )

    if file_path:
        cleanup_all_files(file_path)

    try: await query.message.delete()
    except: pass
    
    context.user_data.clear()
    return ConversationHandler.END
async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    if not query: return

    clean_id = query.replace("audio:", "").replace("voice:", "")
    results = []
    
    try:
        if query.startswith("voice:"):
            results.append(
                InlineQueryResultCachedVoice(
                    id=str(os.urandom(8)),
                    voice_file_id=clean_id,
                    title="Voice Message"
                )
            )

        elif query.startswith("audio:"):
            results.append(
                InlineQueryResultCachedAudio(
                    id=str(os.urandom(8)),
                    audio_file_id=clean_id,
                    caption="🔥 Edited by Music Bot"
                )
            )

        else:
            results.append(
                InlineQueryResultCachedDocument(
                    id=str(os.urandom(8)),
                    title="Music File",
                    document_file_id=clean_id,
                    caption="📂 فایل ویرایش شده"
                )
            )

        await update.inline_query.answer(results, cache_time=1)
        
    except Exception as e:
        print(f"⚠️ Inline Error 1 (Audio failed): {e}")
        
        try:
            fallback_results = [
                InlineQueryResultCachedDocument(
                    id=str(os.urandom(8)),
                    title="Download File",
                    document_file_id=clean_id,
                    caption="📂 دانلود فایل (فرمت خاص)"
                )
            ]
            await update.inline_query.answer(fallback_results, cache_time=1)
            print("✅ Recovered with Document type.")
        except Exception as e2:
            print(f"❌ Critical Inline Error: {e2}")

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = context.user_data.get('file_path')
    user_id = update.effective_user.id

    if file_path:
        cleanup_all_files(file_path)

    context.user_data.clear()

    msg_text = get_text(user_id, 'cancelled_cleanup')

    try:
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_caption(
                caption=msg_text,
                reply_markup=None 
            )
        elif update.message:
            await update.message.reply_text(msg_text)
            
    except Exception:
        pass

    return ConversationHandler.END
async def handle_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("⏰ Timeout triggered inside function!") 

    chat_id = context.user_data.get('chat_id')
    panel_id = context.user_data.get('panel_id')
    file_path = context.user_data.get('file_path')
    user_id = update.effective_user.id if update.effective_user else None

    if not chat_id and update.effective_chat:
        chat_id = update.effective_chat.id

    if file_path:
        cleanup_all_files(file_path)

    if chat_id and panel_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=panel_id)
        except Exception:
            pass 

    if chat_id and user_id:
        msg_text = get_text(user_id, 'timeout_msg')
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg_text,
                parse_mode='Markdown'
            )
        except Exception:
            pass

    context.user_data.clear()
    return ConversationHandler.END

async def show_lock_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    panel_id = context.user_data.get('panel_id')
    locked = context.user_data.get('locked_tags', [])

    def state(tag): return "🔒" if tag in locked else "🔓"

    caption = (
        "🔒 **مدیریت قفل تگ‌ها**\n\n"
        "تگ‌های قفل شده در پاکسازی حذف نمی‌شوند.\n"
        "👇 برای تغییر وضعیت کلیک کنید:"
    )

    keyboard = [
        [InlineKeyboardButton(f"خواننده {state('artist')}", callback_data='toggle_lock_artist'), InlineKeyboardButton(f"آهنگ {state('title')}", callback_data='toggle_lock_title')],
        [InlineKeyboardButton(f"آلبوم {state('album')}", callback_data='toggle_lock_album'), InlineKeyboardButton(f"کاور {state('has_cover')}", callback_data='toggle_lock_has_cover')],
        [InlineKeyboardButton(f"کامنت {state('comment')}", callback_data='toggle_lock_comment'), InlineKeyboardButton(f"متن {state('lyrics')}", callback_data='toggle_lock_lyrics')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='goto_advanced')]
    ]
    
    try:
        await context.bot.edit_message_caption(
            chat_id=update.effective_chat.id,
            message_id=panel_id,
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception: pass



async def show_convert_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    panel_id = context.user_data.get('panel_id')
    caption = (
        "🔄 **تبدیل فرمت**\n\n"
        "فرمت خروجی را انتخاب کنید:\n"
        "(فایل اصلی حذف و نسخه جدید جایگزین می‌شود)"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("MP3 (128kbps)", callback_data='convert_mp3_128'),
            InlineKeyboardButton("MP3 (320kbps)", callback_data='convert_mp3_320')
        ],
        [
            InlineKeyboardButton("FLAC (Lossless)", callback_data='convert_flac'),
            InlineKeyboardButton("WAV (Uncompressed)", callback_data='convert_wav')
        ],
        [
            InlineKeyboardButton("🎵 OGG (Telegram Optimized)", callback_data='convert_ogg')
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='goto_advanced')]
    ]
    
    query = update.callback_query
    await query.edit_message_caption(
        caption="🛠 **تبدیل فرمت**\n\nفرمت مقصد را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def fast_finish_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    status_msg = await update.message.reply_text(get_text(user_id, 'fast_mode_active'))
    
    file_path = context.user_data.get('file_path')
    display_filename = context.user_data.get('filename', 'music.mp3')
    
    selected_channels = get_selected_channels(user_id)

    thumb_path = None
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    import random
                    thumb_path = file_path.replace(".mp3", f"_thumb_{random.randint(1000,9999)}.jpg")
                    with open(thumb_path, "wb") as f:
                        f.write(tag.data)
                    break
    except Exception as e:
        print(f"Thumb extraction error: {e}")

    sent_count = 0
    try:
        with open(file_path, 'rb') as audio_file:
            thumb_file = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
            
            await context.bot.send_audio(
                chat_id=update.effective_chat.id,
                audio=audio_file,
                filename=display_filename,
                caption=get_text(user_id, 'fast_audio_caption'),
                thumbnail=thumb_file, 
                title=context.user_data.get('title', ''), 
                performer=context.user_data.get('artist', '') 
            )
            
            if selected_channels:
                for ch_id in selected_channels:
                    try:
                        audio_file.seek(0)
                        if thumb_file: thumb_file.seek(0)
                        
                        await context.bot.send_audio(
                            chat_id=ch_id,
                            audio=audio_file,
                            filename=display_filename,
                            thumbnail=thumb_file,
                            caption=get_text(user_id, 'channel_caption') 
                        )
                        sent_count += 1
                    except Exception as e:
                        print(f"Failed to send to channel {ch_id}: {e}")

            if thumb_file: thumb_file.close()
            
            if sent_count > 0:
                await update.message.reply_text(get_text(user_id, 'fast_sent_channels').format(count=sent_count))
            
    except Exception as e:
        await update.message.reply_text(get_text(user_id, 'send_error').format(e=e))

    if thumb_path and os.path.exists(thumb_path): 
        try: os.remove(thumb_path)
        except: pass
        
    cleanup_all_files(file_path)
    try: await status_msg.delete()
    except: pass
    context.user_data.clear()
def get_thumb_path(file_path):
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC
    
    thumb_path = file_path.replace(".mp3", ".jpg")
    

    try:
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    with open(thumb_path, "wb") as f:
                        f.write(tag.data)
                    return thumb_path
    except:
        pass
    
    return None
