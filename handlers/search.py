import asyncio
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from utils.locales import get_text
from utils.states import WAITING_SEARCH_QUERY, SELECT_ACTION
from handlers.editor import safe_delete
from utils.task_manager import with_task_protection

def _perform_yt_search(query, pool_size=15):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'skip_download': True,
        'socket_timeout': 15,
        'no_warnings': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(f"ytsearch{pool_size}:{query}", download=False)
        if not result or 'entries' not in result:
            return []
        valid_videos = []
        for entry in result['entries']:
            if not entry:
                continue
            url = entry.get('webpage_url', entry.get('url', ''))
            if '/channel/' in url or '/c/' in url or '/user/' in url or '@' in url.split('/')[-1]:
                continue
            if entry.get('duration') is None or entry.get('duration') == 0:
                continue
            valid_videos.append(entry)
        return valid_videos

@with_task_protection("action")
async def ask_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')]]
    await query.edit_message_text(
        text=get_text(user_id, 'search_prompt'),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return WAITING_SEARCH_QUERY

async def receive_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    search_text = update.message.text.strip()
    if not search_text:
        return WAITING_SEARCH_QUERY
    msg = await update.message.reply_text(get_text(user_id, 'search_searching'))
    try:
        results = await asyncio.to_thread(_perform_yt_search, search_text)
        if not results:
            await msg.edit_text(get_text(user_id, 'search_no_results'))
            return ConversationHandler.END
        context.user_data['search_results'] = results
        context.user_data['search_index'] = 0
        context.user_data['search_visible_limit'] = min(5, len(results))
        await safe_delete(msg)
        await display_search_result(update, context)
        return SELECT_ACTION
    except Exception:
        await msg.edit_text(get_text(user_id, 'search_error'))
        return ConversationHandler.END

async def display_search_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    results = context.user_data.get('search_results', [])
    index = context.user_data.get('search_index', 0)
    visible_limit = context.user_data.get('search_visible_limit', 5)
    if not results:
        return
    flat_result = results[index]
    video_url = flat_result.get('webpage_url', flat_result.get('url')) or f"https://www.youtube.com/watch?v={flat_result.get('id')}"
    if update.callback_query:
        try:
            await update.callback_query.answer("🖼 Loading metadata...")
        except Exception:
            pass
    try:
        ydl_opts = {'quiet': True, 'skip_download': True, 'no_warnings': True, 'socket_timeout': 10}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            full_result = await asyncio.to_thread(ydl.extract_info, video_url, download=False)
    except Exception:
        full_result = flat_result
    context.user_data['yt_url'] = video_url
    context.user_data['yt_title'] = full_result.get('title', flat_result.get('title', 'Unknown'))
    duration_str = full_result.get('duration_string')
    if not duration_str and full_result.get('duration'):
        mins, secs = divmod(int(full_result['duration']), 60)
        duration_str = f"{mins:02d}:{secs:02d}"
    if not duration_str:
        duration_str = "00:00"
    caption = get_text(user_id, 'search_panel').format(
        current=index + 1,
        total=visible_limit,
        title=context.user_data['yt_title'],
        channel=full_result.get('uploader', full_result.get('channel', 'Unknown')),
        duration=duration_str,
        views=full_result.get('view_count') or 0
    )
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton(get_text(user_id, 'btn_prev'), callback_data='search_prev'))
    if index < visible_limit - 1:
        nav_buttons.append(InlineKeyboardButton(get_text(user_id, 'btn_next'), callback_data='search_next'))
    keyboard = [nav_buttons]
    if index == visible_limit - 1 and visible_limit < len(results):
        keyboard.append([InlineKeyboardButton(get_text(user_id, 'btn_load_more'), callback_data='search_load_more')])
    keyboard.extend([
        [
            InlineKeyboardButton(get_text(user_id, 'yt_edit_320'), callback_data='ytdl_edit_320'),
            InlineKeyboardButton(get_text(user_id, 'yt_edit_128'), callback_data='ytdl_edit_128')
        ],
        [
            InlineKeyboardButton(get_text(user_id, 'yt_dir_320'), callback_data='ytdl_dir_320'),
            InlineKeyboardButton(get_text(user_id, 'yt_dir_128'), callback_data='ytdl_dir_128')
        ],
        [InlineKeyboardButton(get_text(user_id, 'btn_cancel'), callback_data='cancel')]
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)
    thumb = full_result.get('thumbnail') or full_result.get('thumbnails', [{}])[-1].get('url')
    if update.callback_query:
        query = update.callback_query
        try:
            await query.message.delete()
        except Exception:
            pass
        if thumb:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=thumb, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=caption, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        if thumb:
            await update.message.reply_photo(photo=thumb, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text=caption, reply_markup=reply_markup, parse_mode='Markdown')

@with_task_protection("action")
async def handle_search_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    results = context.user_data.get('search_results', [])
    visible_limit = context.user_data.get('search_visible_limit', 5)
    if data == 'search_prev':
        context.user_data['search_index'] = max(0, context.user_data.get('search_index', 0) - 1)
    elif data == 'search_next':
        context.user_data['search_index'] = min(visible_limit - 1, context.user_data.get('search_index', 0) + 1)
    elif data == 'search_load_more':
        new_limit = min(visible_limit + 5, len(results))
        context.user_data['search_visible_limit'] = new_limit
        context.user_data['search_index'] = visible_limit
    await display_search_result(update, context)
