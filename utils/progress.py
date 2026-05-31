import asyncio
import io
import math
import os
import time


class TransferProgress:
    def __init__(self, bot, chat_id, message_id=None, operation_type="Processing", media_title="Unknown", artist="Unknown", source="Unknown"):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id
        self.operation_type = operation_type
        self.media_title = media_title
        self.artist = artist
        self.source = source
        self.start_time = time.time()
        self.last_update_time = 0
        self.update_interval = 2.0
        self.total_size = 0
        self.downloaded_size = 0
        self.speed = 0
        self.eta = 0
        self.status = "Starting..."
        self.is_cancelled = False
        self.is_completed = False

    def restart(self, operation_type=None, status=None, total_size=0):
        if operation_type:
            self.operation_type = operation_type
        if status:
            self.status = status
        self.start_time = time.time()
        self.last_update_time = 0
        self.total_size = total_size
        self.downloaded_size = 0
        self.speed = 0
        self.eta = 0
        self.is_cancelled = False
        self.is_completed = False

    def format_size(self, size):
        if not size or size < 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        index = min(int(math.floor(math.log(size, 1024))), len(units) - 1)
        return f"{round(size / math.pow(1024, index), 2)} {units[index]}"

    def format_time(self, seconds):
        if not seconds or seconds < 0:
            return "00:00"
        minutes, secs = divmod(int(seconds), 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def build_text(self):
        separator = "━━━━━━━━━━━━━━━━━━━━"
        if self.is_cancelled:
            return f"{separator}\n❌ Operation Cancelled\nProgress stopped.\n{separator}"
        if self.is_completed:
            return (
                f"{separator}\n"
                f"✅ Completed Successfully\n"
                f"🎵 Title: {self.media_title}\n"
                f"📦 Size: {self.format_size(self.total_size)}\n"
                f"⚡ Average Speed: {self.format_size(self.speed)}/s\n"
                f"⏱ Total Time: {self.format_time(time.time() - self.start_time)}\n"
                f"Ready for next action.\n"
                f"{separator}"
            )
        percentage = 0
        if self.total_size > 0:
            percentage = min(100, max(0, int(self.downloaded_size / self.total_size * 100)))
        filled = percentage // 10
        bar = "█" * filled + "░" * (10 - filled)
        return (
            f"{separator}\n"
            f"🚀 {self.operation_type} Progress\n"
            f"🎵 Title: {self.media_title}\n"
            f"👤 Artist: {self.artist}\n"
            f"🌐 Source: {self.source}\n"
            f"📦 Size: {self.format_size(self.downloaded_size)} / {self.format_size(self.total_size)}\n"
            f"⚡ Speed: {self.format_size(self.speed)}/s\n"
            f"📈 Progress: {percentage}%\n"
            f"{bar}\n"
            f"⏱ ETA: {self.format_time(self.eta)}\n"
            f"🕒 Elapsed: {self.format_time(time.time() - self.start_time)}\n"
            f"🔄 Status:\n{self.status}\n"
            f"{separator}"
        )

    async def update_message(self, force=False):
        now = time.time()
        if not force and now - self.last_update_time < self.update_interval:
            return
        self.last_update_time = now
        await self._edit_message()

    async def _edit_message(self):
        try:
            if self.message_id:
                await self.bot.edit_message_text(chat_id=self.chat_id, message_id=self.message_id, text=self.build_text())
            else:
                message = await self.bot.send_message(chat_id=self.chat_id, text=self.build_text())
                self.message_id = message.message_id
        except Exception:
            pass

    def update_sync(self, downloaded, total, speed, eta, status=None, loop=None):
        self.downloaded_size = downloaded or 0
        if total:
            self.total_size = total
        self.speed = speed or 0
        self.eta = eta or 0
        if status:
            self.status = status
        now = time.time()
        if loop and self.message_id and now - self.last_update_time >= self.update_interval:
            self.last_update_time = now
            asyncio.run_coroutine_threadsafe(
                self._edit_message(),
                loop,
            )

    def yt_dlp_hook(self, data, loop=None):
        if data.get("status") == "downloading":
            self.update_sync(
                data.get("downloaded_bytes", 0),
                data.get("total_bytes") or data.get("total_bytes_estimate", 0),
                data.get("speed", 0),
                data.get("eta", 0),
                "Downloading audio stream...",
                loop,
            )
        elif data.get("status") == "finished":
            total = data.get("total_bytes") or self.total_size or data.get("downloaded_bytes", 0)
            self.update_sync(total, total, 0, 0, "Processing files...", loop)

    async def complete(self):
        elapsed = max(time.time() - self.start_time, 0.001)
        if self.total_size and not self.downloaded_size:
            self.downloaded_size = self.total_size
        if self.downloaded_size:
            self.speed = self.downloaded_size / elapsed
        self.eta = 0
        self.is_completed = True
        await self.update_message(force=True)

    async def cancel(self):
        self.is_cancelled = True
        await self.update_message(force=True)


class IndeterminateProgress:
    def __init__(self, progress):
        self.progress = progress
        self.task = None

    async def _loop(self):
        while not self.progress.is_completed and not self.progress.is_cancelled:
            await self.progress.update_message(force=True)
            await asyncio.sleep(self.progress.update_interval)

    def start(self):
        self.task = asyncio.create_task(self._loop())

    def stop(self):
        if self.task:
            self.task.cancel()
            self.task = None


class ProgressBufferedReader(io.BufferedReader):
    def __init__(self, file_path, progress):
        super().__init__(open(file_path, "rb", buffering=0))
        self.progress = progress
        self.progress.restart("Uploading", "Uploading to Telegram...", os.path.getsize(file_path))
        self.loop = asyncio.get_running_loop()

    def read(self, size=-1):
        data = super().read(size)
        if data:
            self.progress.downloaded_size += len(data)
            elapsed = max(time.time() - self.progress.start_time, 0.001)
            self.progress.speed = self.progress.downloaded_size / elapsed
            remaining = self.progress.total_size - self.progress.downloaded_size
            self.progress.eta = max(remaining / self.progress.speed, 0)
            now = time.time()
            if self.progress.message_id and now - self.progress.last_update_time >= self.progress.update_interval:
                self.progress.last_update_time = now
                asyncio.run_coroutine_threadsafe(
                    self.progress._edit_message(),
                    self.loop,
                )
        return data

    def seek(self, offset, whence=0):
        if offset == 0 and whence == 0:
            self.progress.restart("Uploading", "Uploading to Telegram...", self.progress.total_size)
        return super().seek(offset, whence)
