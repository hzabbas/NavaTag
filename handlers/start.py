from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.user_service import add_user

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE , edit=False):

    user = update.effective_user
    add_user(user.id, user.username, user.full_name)
    
    keyboard = [
        [
            InlineKeyboardButton("🎵 راهنما", callback_data='help'),
            InlineKeyboardButton("📢 کانال ما", url='https://t.me/VoidSuspended')
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
        f"درود {user.first_name}، به **NavaTag** خوش آمدید. 🌑\n\n"
        "اینجا، ابزاری دقیق برای مدیریت متادیتای فایل‌های صوتی شماست.\n"
        "قابلیت‌هایی که در اختیار دارید:\n\n"
        "• ویرایش کامل تگ‌های ID3 (عنوان، هنرمند، آلبوم و...)\n"
        "• مدیریت متمرکز کاور آرت و متن آهنگ (Lyrics)\n"
        "• ابزارهای پیشرفته مانند برش صوتی، تبدیل فرمت و نام‌گذاری استاندارد\n\n"
        "📂 فایل صوتی خود را جهت شروع فرآیند ارسال کنید."
    )

    if edit and update.callback_query:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_text, reply_markup=reply_markup, parse_mode='Markdown')