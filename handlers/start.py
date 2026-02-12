from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.user_service import add_user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE , edit=False):

    user = update.effective_user
    add_user(user.id, user.username, user.full_name)
    
    keyboard = [
        [
            InlineKeyboardButton("🎵 راهنما", callback_data='help'),
            InlineKeyboardButton("📢 کانال ما", url='https://t.me/YourChannel')
        ],
        [
             InlineKeyboardButton("⚙️ تنظیمات شخصی (جدید)", callback_data='open_settings') 
        ],
        [
            InlineKeyboardButton("👨‍💻 پشتیبانی", callback_data='support')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"سلام {user.first_name} عزیز! 👋\n\n"
        "🎧 من ربات **ویرایشگر تگ موزیک** هستم.\n"
        "می‌تونی فایل‌های MP3 خودت رو برام بفرستی تا:\n\n"
        "✨ نام خواننده و آهنگ رو تغییر بدم\n"
        "🖼 کاور آهنگ رو عوض کنم\n"
        "📅 سال انتشار و آلبوم رو تنظیم کنم\n\n"
        "👇 برای شروع، همین الان یه فایل آهنگ بفرست!"
    )

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, reply_markup=reply_markup, parse_mode='Markdown')