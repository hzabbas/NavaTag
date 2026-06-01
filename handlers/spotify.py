import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp

from config import Config

def _get_spotify_info(url):
    sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())
    track = sp.track(url)
    return {
        'title': track['name'],
        'artist': track['artists'][0]['name'],
        'album': track['album']['name'],
        'cover': track['album']['images'][0]['url'],
        'isrc': track['external_ids'].get('isrc')
    }

def _resolve_spotify_audio(isrc, title, artist, output_path):
    query = f"ytsearch1:\"{isrc}\"" if isrc else f"ytsearch1:{title} {artist} audio"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output_path.rsplit(".", 1)[0]}.%(ext)s',
        'quiet': True,
        'socket_timeout': 15,
        'postprocessors': [
            {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'},
        ]
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([query])
    return output_path
