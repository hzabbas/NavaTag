import math
import time
from functools import wraps
from threading import Lock

from telegram.ext import ConversationHandler

from config import Config


class TaskManager:
    MUTE_DURATION = 60
    SPAM_WINDOW = 5
    MAX_REQUESTS = 4

    def __init__(self, clock=time.monotonic):
        self.active_tasks = {}
        self.user_history = {}
        self.mute_list = {}
        self.last_update_ids = {}
        self._clock = clock
        self._lock = Lock()

    def is_admin(self, user_id):
        return user_id == Config.ADMIN_ID

    def check_spam(self, user_id, update_id=None):
        if user_id is None or self.is_admin(user_id):
            return "ok", 0

        now = self._clock()
        with self._lock:
            if update_id is not None:
                if self.last_update_ids.get(user_id) == update_id:
                    return "ok", 0
                self.last_update_ids[user_id] = update_id

            muted_until = self.mute_list.get(user_id)
            if muted_until is not None:
                if now < muted_until:
                    return "mute", math.ceil(muted_until - now)
                del self.mute_list[user_id]

            history = [
                timestamp
                for timestamp in self.user_history.get(user_id, [])
                if now - timestamp < self.SPAM_WINDOW
            ]
            history.append(now)
            self.user_history[user_id] = history

            count = len(history)
            if count == self.MAX_REQUESTS:
                return "warn1", 0
            if count == self.MAX_REQUESTS + 1:
                return "warn2", 0
            if count >= self.MAX_REQUESTS + 2:
                self.mute_list[user_id] = now + self.MUTE_DURATION
                return "muted_just_now", self.MUTE_DURATION
            return "ok", 0

    def start_task(self, user_id, task_id, task_type):
        if user_id is None:
            return False

        now = self._clock()
        with self._lock:
            if user_id in self.active_tasks:
                # Evict orphaned tasks older than 1 hour
                if now - self.active_tasks[user_id].get("start", 0) > 3600:
                    del self.active_tasks[user_id]
                else:
                    return False
            self.active_tasks[user_id] = {
                "id": task_id,
                "type": task_type,
                "start": now,
            }
            return True
    
    def end_task(self, user_id):
        if user_id is None:
            return

        with self._lock:
            self.active_tasks.pop(user_id, None)
        
def mark_entry_point(func):
    func._is_entry_point = True
    return func


async def _send_warning(update, text):
    try:
        if update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text(text)
    except Exception:
        pass


def with_task_protection(task_type="action", release_task_on_error=False):
    def decorator(func):
        is_entry_point = getattr(func, "_is_entry_point", False)

        @wraps(func)
        async def wrapper(update, context, *args, **kwargs):
            user = update.effective_user
            user_id = user.id if user else None
            callback_data = update.callback_query.data if update.callback_query else None

            if callback_data != "cancel":
                status, remaining = task_manager.check_spam(user_id, update.update_id)
                if status == "mute":
                    await _send_warning(update, f"Muted. Wait {remaining}s.")
                    return None
                if status == "muted_just_now":
                    await _send_warning(update, f"Muted for {remaining}s due to spam.")
                    return None
                if status == "warn1":
                    await _send_warning(update, "Warning 1: Do not spam.")
                    return None
                if status == "warn2":
                    await _send_warning(update, "Warning 2: Stop or be muted.")
                    return None

            acquired = False
            if is_entry_point:
                acquired = task_manager.start_task(user_id, str(update.update_id), task_type)
                if not acquired:
                    await _send_warning(update, "You already have an active task. Please finish it or type /cancel to abort.")
                    return None

            try:
                result = await func(update, context, *args, **kwargs)
            except Exception:
                if release_task_on_error:
                    context.user_data.clear()
                if acquired or release_task_on_error:
                    task_manager.end_task(user_id)
                raise

            # Always release task on terminal ConversationHandler.END regardless of acquisition state
            if result == ConversationHandler.END:
                task_manager.end_task(user_id)
            return result

        return wrapper

    return decorator
 
task_manager = TaskManager()
