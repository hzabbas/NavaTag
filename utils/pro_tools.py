import os
import subprocess
from langdetect import detect
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
from mutagen.flac import FLAC, Picture


def _get_cover(file_path):
    if file_path.lower().endswith(".mp3"):
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    return {
                        "data": tag.data,
                        "mime": tag.mime,
                        "type": tag.type,
                        "desc": tag.desc,
                    }
    elif file_path.lower().endswith(".flac"):
        audio = FLAC(file_path)
        if audio.pictures:
            picture = audio.pictures[0]
            return {
                "data": picture.data,
                "mime": picture.mime,
                "type": picture.type,
                "desc": picture.desc,
            }
    return None


def _set_cover(file_path, cover):
    if file_path.lower().endswith(".mp3"):
        audio = MP3(file_path, ID3=ID3)
        if audio.tags is None:
            audio.add_tags()
        audio.tags.delall("APIC")
        audio.tags.add(APIC(encoding=3, **cover))
        audio.save(v2_version=3)
    elif file_path.lower().endswith(".flac"):
        audio = FLAC(file_path)
        picture = Picture()
        picture.data = cover["data"]
        picture.mime = cover["mime"]
        picture.type = cover["type"]
        picture.desc = cover["desc"]
        audio.clear_pictures()
        audio.add_picture(picture)
        audio.save()

def convert_audio(input_path, output_format, bitrate="320k"):
    try:
        new_path = input_path.rsplit('.', 1)[0] + f".{output_format}"
        tmp_path = f"{new_path}.tmp.{output_format}"
        cover = _get_cover(input_path)
        
        if output_format == "wav":
            cmd = ["ffmpeg", "-y", "-i", input_path, "-c:a", "pcm_s16le", tmp_path]
        elif output_format == "ogg":
            cmd = ["ffmpeg", "-y", "-i", input_path, "-map", "0:a", "-c:a", "libopus", "-b:a", "64k", "-map_metadata", "0", tmp_path]
        elif output_format == "flac":
            cmd = ["ffmpeg", "-y", "-i", input_path, "-map", "0:a", "-c:a", "flac", "-map_metadata", "0", tmp_path]
        elif output_format == "mp3":
            cmd = ["ffmpeg", "-y", "-i", input_path, "-map", "0:a", "-c:a", "libmp3lame", "-b:a", bitrate, "-map_metadata", "0", "-id3v2_version", "3", tmp_path]
        else:
            return None
            
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if cover and output_format in ("mp3", "flac"):
            _set_cover(tmp_path, cover)
        os.replace(tmp_path, new_path)
        
        if os.path.exists(new_path):
            return new_path
        return None
        
    except Exception:
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return None

def detect_lyrics_lang(lyrics_text):
    try:
        if not lyrics_text or len(lyrics_text) < 10:
            return "نامشخص (متن کوتاه)"
        lang = detect(lyrics_text)
        return lang.upper()
    except:
        return "نامشخص"

def generate_standard_filename(tags):
    artist = tags.get('artist', 'Unknown')
    title = tags.get('title', 'Unknown')
    year = tags.get('year', '')
    
    safe_chars = lambda s: "".join([c for c in s if c.isalnum() or c in " -_()"])
    
    filename = f"{safe_chars(artist)} - {safe_chars(title)}"
    if year and len(year) == 4:
        filename += f" ({year})"
    
    filename += ".mp3"
    return filename

def smart_clean_tags(file_path, locked_tags=None):
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC
        from utils.tagger import get_tags, set_tag

        old_tags = get_tags(file_path)

        cover_tag = None
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    cover_tag = APIC(
                        encoding=tag.encoding,
                        mime=tag.mime,
                        type=tag.type,
                        desc=tag.desc,
                        data=tag.data,
                    )
                    break
        
        audio.delete()
        audio.save()
        
        new_id3 = ID3()
        new_id3.save(file_path, v2_version=3)

        for tag in locked_tags or []:
            if tag in old_tags and old_tags[tag] and tag != 'has_cover':
                set_tag(file_path, tag, old_tags[tag])
            
        if 'has_cover' in (locked_tags or []) and cover_tag:
            audio = MP3(file_path, ID3=ID3)
            if audio.tags is None:
                audio.add_tags()
            audio.tags.add(cover_tag)
            audio.save(v2_version=3)

        return True
    except Exception as e:
        print(f"Smart Clean failed: {e}")
        return False
