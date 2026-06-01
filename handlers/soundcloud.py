import os
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

async def handle_soundcloud_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_url = update.message.text.strip()
    url = raw_url.split('?')[0]
    
    user_id = update.effective_user.id
    msg = await update.message.reply_text(get_text(user_id, 'sc_fetching'))

    try:
        info = await DownloadManager.fetch_info(url)
        
        if 'entries' in info or info.get('_type') == 'playlist':
            title = info.get('title', 'SoundCloud Playlist')
            creator = info.get('uploader', 'Unknown')
            tracks_count = info.get('playlist_count', 0)
            
            context.user_data['sc_url'] = url
            context.user_data['sc_title'] = title
            context.user_data['sc_type'] = 'playlist'
            
            caption = get_text(user_id, 'sc_playlist_panel').format(
                title=title, creator=creator, tracks=tracks_count
            )
            keyboard = [
                [InlineKeyboardButton(get_text(user_id, 'sc_pl_dir_320'), callback_data='scdl_dir_320')],
                [InlineKeyboardButton(get_text(user_id, 'sc_pl_dir_128'), callback_data='scdl_dir_128')],
                [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')]
            ]
        else:
            title = info.get('title', 'Unknown Track')
            artist = info.get('uploader', 'Unknown Artist')
            duration = info.get('duration', 0)
            mins, secs = divmod(int(duration), 60)
            duration_str = f"{mins}:{secs:02d}"
            genre = info.get('genre', 'Unknown')
            plays = info.get('view_count', 0)
            
            context.user_data['sc_url'] = url
            context.user_data['sc_title'] = title
            context.user_data['sc_type'] = 'track'
            
            caption = get_text(user_id, 'sc_track_panel').format(
                title=title, artist=artist, duration=duration_str,
                genre=genre, plays=plays
            )
            keyboard = [
                [InlineKeyboardButton(get_text(user_id, 'sc_edit_320'), callback_data='scdl_edit_320')],
                [InlineKeyboardButton(get_text(user_id, 'sc_dir_320'), callback_data='scdl_dir_320')],
                [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')]
            ]

        thumb = info.get('thumbnail')
        if thumb:
            await update.message.reply_photo(photo=thumb, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        await safe_delete(msg)
        return SELECT_ACTION
        
    except Exception as e:
        await msg.edit_text(get_text(user_id, 'sc_error'))
        return ConversationHandler.END


@with_task_protection("action", release_task_on_error=True)
async def process_soundcloud_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    
    action, quality = data.replace('scdl_', '').split('_')
    url = context.user_data.get('sc_url')
    track_title = context.user_data.get('sc_title', 'soundcloud_audio')
    
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
        
    status_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text(user_id, 'sc_downloading'))
    progress = TransferProgress(context.bot, update.effective_chat.id, status_msg.message_id, "Downloading", track_title, "Unknown", "SoundCloud")
    loop = asyncio.get_running_loop()
    
    file_id = os.urandom(8).hex()
    raw_path = os.path.join(Config.DOWNLOAD_PATH, f"{file_id}.mp3")
    
    try:
        await DownloadManager.download_media(url, raw_path, quality, progress, loop)
        await progress.complete()
    except Exception:
        await status_msg.edit_text(get_text(user_id, 'sc_error'))
        cleanup_all_files(raw_path)
        context.user_data.clear()
        task_manager.end_task(user_id)
        return ConversationHandler.END

    context.user_data['chat_id'] = update.effective_chat.id
    context.user_data['file_path'] = raw_path
    context.user_data['changes'] = []
    
    safe_title = "".join([c for c in track_title if c.isalnum() or c in " -_()"])
    if not safe_title:
        safe_title = "soundcloud_audio"
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
                    title=track_title,
                    parse_mode='Markdown'
                )
                for ch_id in selected_channels:
                    try:
                        audio_file.seek(0)
                        await context.bot.send_audio(
                            chat_id=ch_id,
                            audio=audio_file,
                            filename=context.user_data['filename'],
                            caption=final_caption,
                            parse_mode='Markdown'
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