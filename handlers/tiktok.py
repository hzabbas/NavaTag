from TikTokApi import TikTokApi
import os

def _get_tiktok_info(url):
    with TikTokApi() as api:
        video = api.video(url=url)
        info = video.info()
        return {
            'title': info.get('desc', 'tiktok_video'),
            'uploader': info.get('author', {}).get('nickname', 'Unknown'),
            'id': video.id
        }

async def _download_tiktok(video_url, output_path):
    with TikTokApi() as api:
        video = api.video(url=video_url)
        video_bytes = await video.bytes()
        with open(output_path, 'wb') as f:
            f.write(video_bytes)
    return output_path
