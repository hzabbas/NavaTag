from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.user_service import add_user, has_language_set, set_user_setting
from utils.locales import get_text
from utils.task_manager import with_task_protection

@with_task_protection("action")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE , edit=False):
    user = update.effective_user
    add_user(user.id, user.username, user.full_name)
    
    if not has_language_set(user.id):
        keyboard = [
            [
                InlineKeyboardButton("🇮🇷 فارسی", callback_data='set_lang_fa'),
                InlineKeyboardButton("🇺🇸 English", callback_data='set_lang_en')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        text = "لطفاً زبان خود را انتخاب کنید:\n\nPlease select your language:"
        
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        return

    keyboard = [
        [
            InlineKeyboardButton(get_text(user.id, 'search_btn'), callback_data='search_song')
        ],
        [
            InlineKeyboardButton(get_text(user.id, 'help_btn'), callback_data='help'),
            InlineKeyboardButton(get_text(user.id, 'channel_btn'), url='https://t.me/VoidSuspended')
        ],
        [
             InlineKeyboardButton(get_text(user.id, 'settings_btn'), callback_data='open_settings') 
        ],
        [
            InlineKeyboardButton(get_text(user.id, 'support_btn'), url='https://t.me/A_HZ81')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = get_text(user.id, 'welcome').format(name=user.first_name)

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

@with_task_protection("action")
async def initial_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    lang = query.data.replace('set_lang_', '')
    
    set_user_setting(user_id, 'language', lang)
    await query.answer("✅")
    await start(update, context, edit=True)

@with_task_protection("action")
async def help_support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if data == 'back_start':
        await start(update, context, edit=True)
        return

    text = get_text(user_id, 'help_text') if data == 'help' else get_text(user_id, 'support_text')
    
    keyboard = [[InlineKeyboardButton(get_text(user_id, 'back_to_start'), callback_data='back_start')]]
    
    await query.answer()
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
