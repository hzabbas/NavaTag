import os
import asyncio
import yt_dlp

class DownloadManager:
    @staticmethod
    def _get_opts(quality=None, is_download=False, output_path=None, progress=None, loop=None):
        opts = {
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 20,
            'cookiefile': 'cookies.txt',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate'
            }
        }
        if not is_download:
            opts['skip_download'] = True
        else:
            out_base = output_path.rsplit('.', 1)[0]
            opts['format'] = 'bestaudio/best'
            opts['outtmpl'] = f'{out_base}.%(ext)s'
            opts['writethumbnail'] = True
            opts['postprocessors'] = [
                {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality},
                {'key': 'FFmpegMetadata', 'add_metadata': True},
                {'key': 'EmbedThumbnail', 'already_have_thumbnail': False},
            ]
            opts['postprocessor_args'] = {'ffmpeg': ['-id3v2_version', '3']}
            if progress and loop:
                opts['progress_hooks'] = [lambda d: progress.yt_dlp_hook(d, loop)]
        return opts

    @staticmethod
    async def fetch_info(url: str):
        def extract():
            with yt_dlp.YoutubeDL(DownloadManager._get_opts(is_download=False)) as ydl:
                return ydl.extract_info(url, download=False)
        return await asyncio.to_thread(extract)

    @staticmethod
    async def download_media(url: str, output_path: str, quality: str, progress=None, loop=None):
        def download():
            opts = DownloadManager._get_opts(quality, True, output_path, progress, loop)
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            return output_path
        return await asyncio.to_thread(download)
