import os
from langdetect import detect
from pydub import AudioSegment
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

def convert_audio(input_path, output_format, bitrate="320k"):
    try:
        audio = AudioSegment.from_file(input_path)
        new_path = input_path.rsplit('.', 1)[0] + f".{output_format}"
        
        params = {"format": output_format}
        
        if output_format == "mp3":
            params["bitrate"] = bitrate
            
        elif output_format == "ogg":
            params["bitrate"] = "64k" 
            params["codec"] = "libopus" 
            
        audio.export(new_path, **params)
        return new_path
        
    except Exception as e:
        print(f"Conversion Error: {e}")
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

def smart_clean_tags(file_path, locked_tags=[]):
    try:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, APIC
        from utils.tagger import get_tags, set_tag, set_cover_from_file

        old_tags = get_tags(file_path)
        
        audio = MP3(file_path)
        audio.delete()
        audio.save()
        
        new_id3 = ID3()
        new_id3.save(file_path, v2_version=3)

        for tag in locked_tags:
            if tag in old_tags and old_tags[tag] and tag != 'has_cover':
                set_tag(file_path, tag, old_tags[tag])
            
            if tag == 'has_cover' and old_tags['has_cover']:
                pass 

        return True
    except Exception as e:
        print(f"Smart Clean failed: {e}")
        return False