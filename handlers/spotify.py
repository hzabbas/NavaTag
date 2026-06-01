import os
import json
import urllib.request
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import Config
from database.user_service import get_selected_channels, get_custom_caption
from handlers.editor import show_panel, safe_delete, cleanup_all_files
from utils.locales import get_text
from utils.progress import ProgressBufferedReader, TransferProgress
from utils.states import SELECT_ACTION
from utils.task_manager import task_manager, with_task_protection
from utils.download_manager import DownloadManager

def _get_spotify_info(url):
    oembed_url = f"https://open.spotify.com/oembed?url={url}"
    req = urllib.request.Request(oembed_url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception:
        return {}

async def handle_spotify_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    msg = await update.message.reply_text("⏳ در حال دریافت اطلاعات اسپاتیفای...")

    try:
        info = await asyncio.to_thread(_get_spotify_info, url)
        
        if not info:
            raise Exception("Metadata fetch failed")
            
        track_name = info.get('title') or 'Unknown'
        
        search_query = track_name.replace(" - song and lyrics by", "").strip()
        
        context.user_data['sp_query'] = search_query
        context.user_data['sp_url'] = url
        context.user_data['sp_title'] = search_query

        caption = f"🎵 **{search_query}**\n\n🔍 منبع دانلود: یوتیوب (تطبیق هوشمند)"
        
        keyboard = [
            [
                InlineKeyboardButton("🎧 دانلود و پنل ویرایش", callback_data='spdl_edit_320')
            ],
            [
                InlineKeyboardButton("📥 ارسال سریع مستقیم", callback_data='spdl_dir_320')
            ],
            [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')]
        ]
        
        thumb = info.get('thumbnail_url')
        if thumb:
            await update.message.reply_photo(photo=thumb, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        await safe_delete(msg)
        return SELECT_ACTION
    except Exception:
        await msg.edit_text("❌ خطا در دریافت اطلاعات اسپاتیفای! لطفاً از صحت لینک مطمئن شوید.")
        return ConversationHandler.END

@with_task_protection("action", release_task_on_error=True)
async def process_spotify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    action, quality = data.replace('spdl_', '').split('_')
    search_query = context.user_data.get('sp_query')
    track_title = context.user_data.get('sp_title', 'spotify_audio')
    
    dl_target = f"ytsearch1:{search_query} audio"
    
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
        
    status_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="🚀 Initiating...")
    progress = TransferProgress(context.bot, update.effective_chat.id, status_msg.message_id, "Downloading", track_title, "Unknown", "Spotify")
    loop = asyncio.get_running_loop()
    
    file_id = os.urandom(8).hex()
    raw_path = os.path.join(Config.DOWNLOAD_PATH, f"{file_id}.mp3")
    
    try:
        await DownloadManager.download_media(dl_target, raw_path, quality, progress, loop)
        await progress.complete()
    except Exception:
        await status_msg.edit_text("❌ خطا در استخراج و دانلود فایل صوتی.")
        cleanup_all_files(raw_path)
        context.user_data.clear()
        task_manager.end_task(user_id)
        return ConversationHandler.END

    context.user_data['chat_id'] = update.effective_chat.id
    context.user_data['file_path'] = raw_path
    context.user_data['changes'] = []
    
    safe_title = "".join([c for c in track_title if c.isalnum() or c in " -_()"])
    if not safe_title:
        safe_title = "spotify_audio"
    context.user_data['filename'] = f"{safe_title}.mp3"
    context.user_data['locked_tags'] = []

    if action == 'dir':
        context.user_data['title'] = track_title
        sent_count = 0
        selected_channels = get_selected_channels(user_id)
        custom_caption = get_custom_caption(user_id)
        final_caption = custom_caption if custom_caption else None
        try:
            with ProgressBufferedReader(raw_path, progress) as audio_file:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=audio_file,
                    filename=context.user_data['filename'],
                    caption=final_caption,
                    parse_mode='Markdown',
                    title=track_title
                )
                for ch_id in selected_channels:
                    try:
                        audio_file.seek(0)
                        await context.bot.send_audio(
                            chat_id=ch_id,
                            audio=audio_file,
                            filename=context.user_data['filename'],
                            caption=final_caption,
                            parse_mode='Markdown',
                        )
                        sent_count += 1
                    except Exception:
                        pass
            if sent_count > 0:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=get_text(user_id, 'fast_sent_channels').format(count=sent_count),
                    parse_mode='Markdown'
                )
            await progress.complete()
        except Exception as e:
            await progress.cancel()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=get_text(user_id, 'send_error').format(e=e)
            )
        finally:
            cleanup_all_files(raw_path)
            context.user_data.clear()
            task_manager.end_task(user_id)
        return ConversationHandler.END
    else:
        await safe_delete(status_msg)
        await show_panel(update, context, is_first_time=True)
        return SELECT_ACTION