import os
import asyncio
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import Config
from database.user_service import get_selected_channels
from handlers.editor import show_panel, safe_delete, cleanup_all_files
from utils.locales import get_text
from utils.states import SELECT_ACTION


def _get_ig_info(url):
    ydl_opts = {'quiet': True, 'skip_download': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def _download_ig(url, quality, output_path):
    out_base = output_path.rsplit('.', 1)[0]
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{out_base}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,
        }],
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path


async def handle_instagram_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    msg = await update.message.reply_text(get_text(user_id, 'ig_fetching'))
    try:
        info = await asyncio.to_thread(_get_ig_info, url)
        context.user_data['ig_url'] = url

        raw_title = info.get('title') or info.get('description') or 'Instagram Post'
        title = raw_title.replace('\n', ' ')
        title = title[:50] + "..." if len(title) > 50 else title
        context.user_data['ig_title'] = title

        dur = info.get('duration')
        duration_string = f"{int(dur)//60:02d}:{int(dur)%60:02d}" if dur else '00:00'
        likes = info.get('like_count') or 0

        caption = get_text(user_id, 'ig_panel').format(
            title=title,
            channel=info.get('uploader', 'Unknown'),
            duration=duration_string,
            likes=likes
        )
        keyboard = [
            [
                InlineKeyboardButton(get_text(user_id, 'ig_edit_320'), callback_data='igdl_edit_320'),
                InlineKeyboardButton(get_text(user_id, 'ig_edit_128'), callback_data='igdl_edit_128')
            ],
            [
                InlineKeyboardButton(get_text(user_id, 'ig_dir_320'), callback_data='igdl_dir_320'),
                InlineKeyboardButton(get_text(user_id, 'ig_dir_128'), callback_data='igdl_dir_128')
            ],
            [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')]
        ]
        thumb = info.get('thumbnail')
        if thumb:
            await update.message.reply_photo(photo=thumb, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        await safe_delete(msg)
        return SELECT_ACTION
    except Exception:
        await msg.edit_text(get_text(user_id, 'ig_error'))
        return ConversationHandler.END


async def process_instagram_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    data = query.data
    action, quality = data.replace('igdl_', '').split('_')
    url = context.user_data.get('ig_url')
    title = context.user_data.get('ig_title', 'instagram_audio')
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    status_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text(user_id, 'ig_downloading'))
    file_id = os.urandom(8).hex()
    raw_path = os.path.join(Config.DOWNLOAD_PATH, f"{file_id}.mp3")
    try:
        await asyncio.to_thread(_download_ig, url, quality, raw_path)
    except Exception:
        await status_msg.edit_text(get_text(user_id, 'ig_error'))
        return ConversationHandler.END

    context.user_data['chat_id'] = update.effective_chat.id
    context.user_data['file_path'] = raw_path
    context.user_data['changes'] = []
    safe_title = "".join([c for c in title if c.isalnum() or c in " -_()"])
    if not safe_title:
        safe_title = "instagram_audio"
    context.user_data['filename'] = f"{safe_title}.mp3"
    context.user_data['locked_tags'] = []

    if action == 'dir':
        context.user_data['title'] = title
        sent_count = 0
        selected_channels = get_selected_channels(user_id)
        try:
            with open(raw_path, 'rb') as audio_file:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=audio_file,
                    filename=context.user_data['filename'],
                    caption=get_text(user_id, 'fast_audio_caption'),
                    title=title
                )
                for ch_id in selected_channels:
                    try:
                        audio_file.seek(0)
                        await context.bot.send_audio(
                            chat_id=ch_id,
                            audio=audio_file,
                            filename=context.user_data['filename'],
                            caption=get_text(user_id, 'channel_caption')
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
        except Exception as e:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=get_text(user_id, 'send_error').format(e=e)
            )
        finally:
            await safe_delete(status_msg)
            cleanup_all_files(raw_path)
            context.user_data.clear()
        return ConversationHandler.END
    else:
        await safe_delete(status_msg)
        await show_panel(update, context, is_first_time=True)
        return SELECT_ACTION
