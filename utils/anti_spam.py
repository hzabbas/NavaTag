import time
from collections import defaultdict
from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop
from config import Config

_user_data = defaultdict(lambda: {'requests': [], 'ban_until': 0, 'offense_count': 0, 'last_offense': 0, 'last_message': 0})
SPAM_LIMIT = 5
TIME_WINDOW = 4
PENALTIES = [120, 300, 900]
RESET_TIME = 24 * 3600

async def spam_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return
    user_id = update.effective_user.id
    if user_id == Config.ADMIN_ID:
        return
    now = time.time()
    data = _user_data[user_id]
    if now < data['ban_until']:
        raise ApplicationHandlerStop
    if now - data['last_message'] > RESET_TIME:
        data['offense_count'] = 0
        data['requests'] = []
    data['last_message'] = now
    requests = data['requests']
    requests.append(now)
    data['requests'] = [t for t in requests if t > now - TIME_WINDOW]
    if len(data['requests']) > SPAM_LIMIT:
        data['offense_count'] += 1
        data['last_offense'] = now
        if data['offense_count'] <= len(PENALTIES):
            penalty = PENALTIES[data['offense_count'] - 1]
        else:
            penalty = PENALTIES[-1] + (data['offense_count'] - len(PENALTIES)) * 600
        data['ban_until'] = now + penalty
        data['requests'] = []
        try:
            await context.bot.send_message(chat_id=user_id, text=f"⚠️ **سیستم امنیتی:**\nشما به مدت {int(penalty)} ثانیه محدود شده‌اید.", parse_mode='Markdown')
            admin_text = (
                "🚨 **سیستم دفاعی نواتگ (Anti-Spam)**\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 کاربر: {update.effective_user.full_name}\n"
                f"🔗 یوزرنیم: @{update.effective_user.username if update.effective_user.username else 'ندارد'}\n"
                f"🆔 شناسه: `{user_id}`\n"
                "⚠️ نوع اختلال: Flood / اسپم\n"
                f"🛑 محدودیت اعمال شده: {int(penalty)} ثانیه موقت\n"
                "━━━━━━━━━━━━━━━━━━━━"
            )
            await context.bot.send_message(chat_id=Config.ADMIN_ID, text=admin_text, parse_mode='Markdown')
        except Exception:
            pass
        raise ApplicationHandlerStop
