from multiprocessing import context
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup , InputMediaPhoto , InlineQueryResultCachedAudio, InlineQueryResultCachedVoice , InlineQueryResultCachedDocument
from telegram.ext import ContextTypes, ConversationHandler
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from config import Config
from pydub import AudioSegment
from database.user_service import (
    add_channel, 
    get_user_channels, 
    toggle_channel_selection, 
    delete_channel, 
    get_selected_channels
)
from telegram import InlineQueryResultCachedAudio
from utils.states import SELECT_ACTION, WAITING_INPUT, WAITING_COVER, WAITING_CHANNEL
from utils.tagger import get_tags, set_tag, set_cover_from_file, delete_all_tags , apply_tags
from utils.pro_tools import convert_audio, detect_lyrics_lang, generate_standard_filename, smart_clean_tags
try:
    from utils.pro_tools import convert_audio, detect_lyrics_lang, generate_standard_filename, smart_clean_tags
except ImportError:
    pass



def cleanup_all_files(file_path):
    if not file_path: return
    
    base_path = os.path.splitext(file_path)[0]
    
    extensions = ['.mp3', '.ogg', '.wav', '.flac', '.jpg', '.png']
    
    for ext in extensions:
        target = base_path + ext
        if os.path.exists(target):
            try:
                os.remove(target)
                print(f"🧹 Deleted: {target}")
            except Exception as e:
                print(f"⚠️ Error deleting {target}: {e}")



async def start_editor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    context.user_data['chat_id'] = update.effective_chat.id
    msg = await update.message.reply_text("⏳ در حال دانلود و آنالیز...")
    
    file_id = update.message.audio.file_id
    new_file = await context.bot.get_file(file_id)
    file_path = os.path.join(Config.DOWNLOAD_PATH, f"{update.message.audio.file_unique_id}.mp3")
    await new_file.download_to_drive(file_path)

    context.user_data['file_path'] = file_path
    context.user_data['changes'] = []
    context.user_data['filename'] = update.message.audio.file_name or "music.mp3"
    context.user_data['locked_tags'] = []

    try: await msg.delete()
    except: pass

    await show_panel(update, context, is_first_time=True)
    
    print("✅ Start Editor Finished! Returning State 0") 
    return SELECT_ACTION

async def show_panel(update: Update, context: ContextTypes.DEFAULT_TYPE, is_first_time=False):
    file_path = context.user_data.get('file_path')
    if not file_path:
        return

    panel_id = context.user_data.get('panel_id')
    changes = context.user_data.get('changes', [])
    chat_id = update.effective_chat.id
    tags = get_tags(file_path)

    def mark(tag_name): return "✏️" if tag_name in changes else ""
    
    caption = (
        f"🎧 **Music Editor Panel**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📏 Size: `{tags['size']}`\n"
        f"⏱ Duration: `{tags['duration']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Artist: `{tags['artist']}` {mark('artist')}\n"
        f"🎵 Title: `{tags['title']}` {mark('title')}\n"
        f"💿 Album: `{tags['album']}` {mark('album')}\n"
        f"🎹 Genre: `{tags['genre']}` {mark('genre')}\n"
        f"📅 Year: `{tags['year']}` {mark('year')}\n"
        f"🔢 Track: `{tags.get('track', '0')}` {mark('track')}\n"
        f"📝 Lyrics: {'✅ دارد' if tags.get('lyrics') else '❌ ندارد'} {mark('lyrics')}\n"
        f"🖼 Cover: {'✅ دارد' if tags.get('has_cover') else '❌ ندارد'} {mark('has_cover')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 بخش مورد نظر را انتخاب کنید:"
    )

    keyboard = [
        [InlineKeyboardButton("🎵 نام آهنگ", callback_data='edit_title'), InlineKeyboardButton("👤 خواننده", callback_data='edit_artist')],
        [InlineKeyboardButton("🎹 ژانر", callback_data='edit_genre'), InlineKeyboardButton("💿 آلبوم", callback_data='edit_album')],
        [InlineKeyboardButton("🔢 شماره ترک", callback_data='edit_track'), InlineKeyboardButton("📅 سال", callback_data='edit_year')],
        [InlineKeyboardButton("💬 کامنت", callback_data='edit_comment'), InlineKeyboardButton("📝 متن آهنگ", callback_data='edit_lyrics')],
        [InlineKeyboardButton("🖼 عکس کاور", callback_data='edit_cover'), InlineKeyboardButton("🚀 پیشرفته (VIP)", callback_data='goto_advanced')],
        [InlineKeyboardButton("❌ لغو", callback_data='cancel'), InlineKeyboardButton("✅ اعمال و آپلود", callback_data='done')]
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
    
    caption = (
        f"🚀 **Advanced Pro Tools**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📁 فایل فعلی: `{current_filename}`\n"
        f"🛠 ابزار مورد نظر را انتخاب کنید:\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("🔄 تبدیل فرمت", callback_data='menu_convert'),
            InlineKeyboardButton("🧹 پاکسازی حرفه‌ای", callback_data='pro_clean')
        ],
        [
            InlineKeyboardButton("✂️ برش آهنگ (Cutter)", callback_data='start_cut'),
            InlineKeyboardButton("📝 نام‌گذاری استاندارد", callback_data='auto_rename')
        ],
        [
            InlineKeyboardButton("🔒 قفل تگ‌ها", callback_data='menu_lock'),
            InlineKeyboardButton("🌐 تشخیص زبان", callback_data='detect_lang')
        ],
        [
            InlineKeyboardButton("✏️ تغییر نام فایل", callback_data='edit_filename'),
            InlineKeyboardButton("📢 مدیریت کانال‌ها (VIP)", callback_data='manage_channels')
        ],
        [
            InlineKeyboardButton("🎙 تبدیل به ویس (Voice)", callback_data='convert_to_voice') # 👈 دکمه جدید
        ],
        [
            InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data='goto_main')
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
        await query.answer("❌ ربات ریست شده. آهنگ را دوباره بفرستید.", show_alert=True)
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
        await query.answer("عملیات لغو شد ❌")
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
        keyboard = [[InlineKeyboardButton("🔙 انصراف", callback_data='mode_view')]] 
        msg = await query.message.reply_text(
            "➕ **افزودن کانال جدید**\n\n"
            "آیدی کانال را بفرستید (مثل @Channel) یا یک پیام از آن **فوروارد** کنید.\n"
            "⚠️ ربات باید در آن کانال ادمین باشد.",
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
        await query.answer("🗑 کانال حذف شد.", show_alert=False)
        await show_channels_menu(update, context, mode='delete') 
        return SELECT_ACTION


    if data == 'start_cut':
        await query.answer()
        msg = await query.message.reply_text(
            "✂️ **ابزار برش حرفه‌ای (Cutter)**\n\n"
            "لطفاً بازه زمانی را بفرستید. مثال: `00:30-01:15` ",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data='goto_advanced')]])
        )
        context.user_data['msg_to_delete'] = msg.message_id
        context.user_data['current_tag'] = 'cut_audio'
        return WAITING_INPUT

    if data == 'menu_convert': await show_convert_menu(update, context); return SELECT_ACTION
    if data == 'menu_lock': await show_lock_menu(update, context); return SELECT_ACTION


    if data == 'convert_to_voice':
        await query.answer("⏳ در حال تبدیل به ویس...")
        
        current_path = context.user_data.get('file_path')
        
        voice_path = convert_audio(current_path, "ogg", bitrate="64k")
        
        if voice_path:
            if current_path != voice_path and os.path.exists(current_path):
                try: os.remove(current_path)
                except: pass
            
            context.user_data['file_path'] = voice_path
            context.user_data['is_voice'] = True
            
            with open(voice_path, 'rb') as f:
                await query.message.reply_voice(
                    voice=f,
                    caption="✅ تبدیل به ویس انجام شد."
                )
            
            await show_advanced_panel(update, context)
        else:
            await query.answer("❌ خطا در تبدیل!", show_alert=True)
            
        return SELECT_ACTION

    if data.startswith('convert_'):
        await query.answer("⏳ در حال تبدیل فرمت و انتقال تگ‌ها...")
        
        target = data.replace('convert_', '')
        
        fmt = 'mp3'
        bitrate = '320k'
        if target == 'mp3_128': bitrate = '128k'
        elif target == 'flac': fmt = 'flac'
        elif target == 'wav': fmt = 'wav' 
        elif target == 'ogg': fmt = 'ogg'; bitrate = '128k'

        old_tags = get_tags(file_path) 
        
        new_path = convert_audio(file_path, fmt, bitrate)
        
        if new_path:
            if os.path.exists(file_path) and file_path != new_path:
                try: os.remove(file_path)
                except: pass
            
            if fmt != 'wav':
                apply_tags(new_path, old_tags)
            
            context.user_data['file_path'] = new_path
            
            old_name = context.user_data.get('filename', 'music.mp3')
            base_name = os.path.splitext(old_name)[0]
            context.user_data['filename'] = f"{base_name}.{fmt}"
            
            await query.answer(f"✅ تبدیل به {fmt.upper()} با موفقیت انجام شد!", show_alert=True)
            await show_advanced_panel(update, context)
        else:
            await query.answer("❌ خطا در تبدیل فرمت!", show_alert=True)
            
        return SELECT_ACTION
    

    if data == 'pro_clean':
        locks = context.user_data.get('locked_tags', [])
        if smart_clean_tags(file_path, locked_tags=locks):
            await query.answer("🧹 فایل پاکسازی شد.", show_alert=True)
        else:
            await query.answer("❌ خطا در پاکسازی.", show_alert=True)
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
        tags = get_tags(file_path)
        new_name = generate_standard_filename(tags)
        context.user_data['filename'] = new_name
        await query.answer(f"📝 نام جدید: {new_name}", show_alert=True)
        await show_advanced_panel(update, context)
        return SELECT_ACTION

    if data == 'detect_lang':
        tags = get_tags(file_path)
        lang = detect_lyrics_lang(tags.get('lyrics'))
        await query.answer(f"🌐 زبان: {lang}", show_alert=True)
        return SELECT_ACTION

    tag_map = {
        'edit_title': 'title', 'edit_artist': 'artist', 'edit_album': 'album',
        'edit_genre': 'genre', 'edit_year': 'year', 'edit_track': 'track',
        'edit_comment': 'comment', 'edit_lyrics': 'lyrics', 'edit_filename': 'filename'
    }
    
    if data in tag_map:
        context.user_data['current_tag'] = tag_map[data]
        tag_fa = data.replace('edit_', '').upper()
        await query.answer(f"👇 مقدار جدید {tag_fa} را بفرستید:", show_alert=False)
        return WAITING_INPUT

    if data == 'edit_cover':
        await query.answer("🖼 عکس کاور را بفرستید 👇", show_alert=False)
        return WAITING_COVER

    return SELECT_ACTION

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
            except: pass

        try: await update.message.delete()
        except: pass

        try:
            start_str, end_str = text.split('-')
            def get_ms(time_str):
                m, s = map(int, time_str.split(':'))
                return (m * 60 + s) * 1000

            start_ms = get_ms(start_str)
            end_ms = get_ms(end_str)

            file_path = context.user_data.get('file_path')
            audio = AudioSegment.from_file(file_path)
            
            if end_ms > len(audio) or start_ms >= end_ms:
                err = await update.message.reply_text("❌ بازه نامعتبر! دوباره بفرستید.")
                context.user_data['msg_to_delete'] = err.message_id
                return WAITING_INPUT

            status_msg = await update.message.reply_text("⏳ در حال برش...")
            
            cut_part = audio[start_ms:end_ms]
            cut_part.export(file_path, format="mp3")

            await status_msg.delete()
            temp_ok = await update.message.reply_text("✅ برش با موفقیت انجام شد!")
            
            await asyncio.sleep(2)
            try: await temp_ok.delete()
            except: pass

            await show_advanced_panel(update, context)
            return SELECT_ACTION

        except Exception as e:
            err = await update.message.reply_text("❌ خطا در فرمت! دوباره تلاش کنید.")
            context.user_data['msg_to_delete'] = err.message_id
            return WAITING_INPUT
        
    if tag_to_edit == 'filename':
        if not new_text.lower().endswith(".mp3"): new_text += ".mp3"
        context.user_data['filename'] = new_text
        msg = await update.message.reply_text(f"✅ نام فایل شد: {new_text}")
        await asyncio.sleep(2)
        try: await msg.delete()
        except: pass
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
        try: await msg.delete()
        except: pass
        return WAITING_INPUT

    success = set_tag(file_path, tag_to_edit, new_text)

    if success:
        if tag_to_edit not in context.user_data['changes']:
            context.user_data['changes'].append(tag_to_edit)
        await show_panel(update, context)
    else:
        msg = await update.message.reply_text("❌ خطا در ویرایش.")
        await asyncio.sleep(3)
        try: await msg.delete()
        except: pass

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
        try: await msg.delete()
        except: pass

    return SELECT_ACTION

async def receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = None
    channel_title = "Unknown Channel"

    if update.message.forward_from_chat and update.message.forward_from_chat.type == 'channel':
        channel_id = update.message.forward_from_chat.id
        channel_title = update.message.forward_from_chat.title
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
        
        if add_channel(update.effective_user.id, final_id, final_title):
            success_msg = await update.message.reply_text(
                f"✅ کانال **{final_title}** با موفقیت تایید و اضافه شد!",
                parse_mode='Markdown'
            )
        else:
            success_msg = await update.message.reply_text("⚠️ این کانال قبلاً در لیست شما وجود دارد.")

        await asyncio.sleep(2)
        try: await success_msg.delete()
        except: pass

        await show_advanced_panel(update, context) 
        return SELECT_ACTION

    except Exception as e:
        err_text = str(e).replace('Exception:', '').strip()
        
        err_msg = await update.message.reply_text(
            f"❌ **خطا:**\n{err_text}\n\n"
            f"👇 مجدداً آیدی صحیح را ارسال کنید یا دکمه انصراف را بزنید.",
            parse_mode='Markdown'
        )
        
        await asyncio.sleep(5)

        try: await err_msg.delete()
        except: pass

        return WAITING_CHANNEL

async def finish_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("در حال آپلود نهایی... 📤")
    
    file_path = context.user_data.get('file_path')
    is_voice = context.user_data.get('is_voice', False)
    display_filename = context.user_data.get('filename', 'music.mp3')
    user_id = update.effective_user.id

    selected_channels = get_selected_channels(user_id)
    
    tags = get_tags(file_path)
    
    report_text = (
        f"🚀 **عملیات با موفقیت به پایان رسید!**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📂 فایل نهایی: `{display_filename}`\n"
        f"📏 حجم: `{tags['size']}`\n"
        f"⏱ زمان: `{tags['duration']}`\n"
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
                    caption=f"✅ ویس شما آماده شد.\n🤖 @YourBotName"
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
                    caption=f"✅ فایل شما آماده شد.\n🤖 @YourBotName",
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

        keyboard.append([InlineKeyboardButton("🚀 ارسال برای دوستان", switch_inline_query=query_data)])
    if selected_channels:
        report_text += f"✅ ارسال به **{sent_count}** کانال انجام شد.\n"

    report_text += f"\n✨ از اینکه از ما استفاده کردید متشکریم!"

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

    if file_path:
        cleanup_all_files(file_path)

    context.user_data.clear()

    msg_text = "❌ عملیات لغو شد و تمام فایل‌های موقت پاکسازی گردیدند."

    try:
        if update.callback_query:
            await update.callback_query.answer("لغو شد")
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

    if not chat_id and update.effective_chat:
        chat_id = update.effective_chat.id

    if file_path:
        cleanup_all_files(file_path)

    if chat_id and panel_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=panel_id)
        except Exception:
            pass 

    if chat_id:
        msg_text = (
            "⏰ **نشست ویرایش منقضی شد!**\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ جهت بهینه‌سازی سرور، فایل موقت و پنل ویرایش شما حذف گردید.\n\n"
            "♻️ **برای شروع مجدد، آهنگ یا ویس خود را دوباره ارسال کنید.**"
        )
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