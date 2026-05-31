import asyncio
import os

import yt_dlp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from config import Config
from database.user_service import get_selected_channels
from handlers.editor import cleanup_all_files, safe_delete, show_panel
from utils.locales import get_text
from utils.states import SELECT_ACTION


def _get_sc_info(url):
    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': 'in_playlist',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def _download_sc(url, quality, output_path):
    out_base = output_path.rsplit('.', 1)[0]
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{out_base}.%(ext)s',
        'writethumbnail': True,
        'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality},
            {'key': 'FFmpegMetadata', 'add_metadata': True},
            {'key': 'EmbedThumbnail', 'already_have_thumbnail': False},
        ],
        'postprocessor_args': {'ffmpeg': ['-id3v2_version', '3']},
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path


def _safe_filename(title, fallback='soundcloud_audio'):
    safe_title = ''.join(c for c in title if c.isalnum() or c in ' -_()').strip()
    return f'{safe_title or fallback}.mp3'


def _entry_url(entry):
    return entry.get('webpage_url') or entry.get('url')


async def handle_soundcloud_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    msg = await update.message.reply_text(get_text(user_id, 'sc_fetching'))

    try:
        info = await asyncio.to_thread(_get_sc_info, url)
        context.user_data['sc_url'] = url
        context.user_data['sc_title'] = info.get('title') or 'Unknown'
        context.user_data['sc_is_playlist'] = info.get('_type') == 'playlist'

        if context.user_data['sc_is_playlist']:
            entries = [
                {
                    'url': _entry_url(entry),
                    'title': entry.get('title') or 'Unknown',
                }
                for entry in info.get('entries', [])
                if _entry_url(entry)
            ]
            if not entries:
                raise ValueError('SoundCloud playlist has no downloadable tracks')

            context.user_data['sc_entries'] = entries
            caption = get_text(user_id, 'sc_playlist_panel').format(
                title=info.get('title') or 'Unknown',
                creator=info.get('uploader') or info.get('creator') or 'Unknown',
                tracks=len(entries),
            )
            keyboard = [
                [
                    InlineKeyboardButton(get_text(user_id, 'sc_pl_dir_320'), callback_data='scdl_pl_320'),
                    InlineKeyboardButton(get_text(user_id, 'sc_pl_dir_128'), callback_data='scdl_pl_128'),
                ],
                [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')],
            ]
        else:
            caption = get_text(user_id, 'sc_track_panel').format(
                title=info.get('title') or 'Unknown',
                artist=info.get('uploader') or info.get('artist') or 'Unknown',
                duration=info.get('duration_string') or '00:00',
                genre=info.get('genre') or 'Unknown',
                plays=info.get('view_count') or 0,
                likes=info.get('like_count') or 0,
                reposts=info.get('repost_count') or 0,
            )
            keyboard = [
                [
                    InlineKeyboardButton(get_text(user_id, 'sc_edit_320'), callback_data='scdl_edit_320'),
                    InlineKeyboardButton(get_text(user_id, 'sc_edit_128'), callback_data='scdl_edit_128'),
                ],
                [
                    InlineKeyboardButton(get_text(user_id, 'sc_dir_320'), callback_data='scdl_dir_320'),
                    InlineKeyboardButton(get_text(user_id, 'sc_dir_128'), callback_data='scdl_dir_128'),
                ],
                [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')],
            ]

        thumb = info.get('thumbnail')
        reply_markup = InlineKeyboardMarkup(keyboard)
        if thumb:
            await update.message.reply_photo(
                photo=thumb,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='Markdown',
            )
        else:
            await update.message.reply_text(
                text=caption,
                reply_markup=reply_markup,
                parse_mode='Markdown',
            )

        await safe_delete(msg)
        return SELECT_ACTION
    except Exception:
        await msg.edit_text(get_text(user_id, 'sc_error'))
        return ConversationHandler.END


async def process_soundcloud_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    action, quality = query.data.replace('scdl_', '', 1).split('_', 1)

    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass

    if action == 'pl':
        return await _download_playlist(update, context, quality)

    return await _download_track(update, context, action, quality)


async def _download_playlist(update: Update, context: ContextTypes.DEFAULT_TYPE, quality):
    user_id = update.effective_user.id
    entries = context.user_data.get('sc_entries', [])
    status_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=get_text(user_id, 'sc_downloading'),
    )
    selected_channels = get_selected_channels(user_id)
    successful_downloads = 0

    for index, entry in enumerate(entries, 1):
        await status_msg.edit_text(
            get_text(user_id, 'sc_pl_progress').format(current=index, total=len(entries))
        )
        raw_path = os.path.join(Config.DOWNLOAD_PATH, f'{os.urandom(8).hex()}.mp3')

        try:
            await asyncio.to_thread(_download_sc, entry['url'], quality, raw_path)
            filename = _safe_filename(entry.get('title') or 'Unknown')

            with open(raw_path, 'rb') as audio_file:
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=audio_file,
                    filename=filename,
                    caption=get_text(user_id, 'fast_audio_caption'),
                    title=entry.get('title') or 'Unknown',
                )
                successful_downloads += 1

                for channel_id in selected_channels:
                    try:
                        audio_file.seek(0)
                        await context.bot.send_audio(
                            chat_id=channel_id,
                            audio=audio_file,
                            filename=filename,
                            caption=get_text(user_id, 'channel_caption'),
                        )
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            cleanup_all_files(raw_path)

    final_text = 'sc_pl_done' if successful_downloads else 'sc_error'
    await status_msg.edit_text(get_text(user_id, final_text))
    context.user_data.clear()
    return ConversationHandler.END


async def _download_track(update: Update, context: ContextTypes.DEFAULT_TYPE, action, quality):
    user_id = update.effective_user.id
    url = context.user_data.get('sc_url')
    title = context.user_data.get('sc_title', 'soundcloud_audio')
    status_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=get_text(user_id, 'sc_downloading'),
    )
    raw_path = os.path.join(Config.DOWNLOAD_PATH, f'{os.urandom(8).hex()}.mp3')

    try:
        await asyncio.to_thread(_download_sc, url, quality, raw_path)
    except Exception:
        cleanup_all_files(raw_path)
        await status_msg.edit_text(get_text(user_id, 'sc_error'))
        return ConversationHandler.END

    context.user_data['chat_id'] = update.effective_chat.id
    context.user_data['file_path'] = raw_path
    context.user_data['changes'] = []
    context.user_data['filename'] = _safe_filename(title)
    context.user_data['locked_tags'] = []

    if action == 'edit':
        await safe_delete(status_msg)
        await show_panel(update, context, is_first_time=True)
        return SELECT_ACTION

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
                title=title,
            )
            for channel_id in selected_channels:
                try:
                    audio_file.seek(0)
                    await context.bot.send_audio(
                        chat_id=channel_id,
                        audio=audio_file,
                        filename=context.user_data['filename'],
                        caption=get_text(user_id, 'channel_caption'),
                    )
                    sent_count += 1
                except Exception:
                    pass

        if sent_count > 0:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=get_text(user_id, 'fast_sent_channels').format(count=sent_count),
                parse_mode='Markdown',
            )
    except Exception as error:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=get_text(user_id, 'send_error').format(e=error),
        )
    finally:
        await safe_delete(status_msg)
        cleanup_all_files(raw_path)
        context.user_data.clear()

    return ConversationHandler.END
