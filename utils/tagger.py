import os
from mutagen import File
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TDRC, TRCK, COMM, USLT, APIC
from mutagen.flac import FLAC
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis


def apply_tags(file_path, tags_dict):
    if not os.path.exists(file_path): return False
    
    try:
        if file_path.lower().endswith(".mp3"):
            audio = MP3(file_path, ID3=ID3)
            if audio.tags is None: audio.add_tags()
            
            if tags_dict.get('title'):
                audio.tags.delall("TIT2")
                audio.tags.add(TIT2(encoding=3, text=tags_dict['title']))
            if tags_dict.get('artist'):
                audio.tags.delall("TPE1")
                audio.tags.add(TPE1(encoding=3, text=tags_dict['artist']))
            if tags_dict.get('album'):
                audio.tags.delall("TALB")
                audio.tags.add(TALB(encoding=3, text=tags_dict['album']))
            if tags_dict.get('genre'):
                audio.tags.delall("TCON")
                audio.tags.add(TCON(encoding=3, text=tags_dict['genre']))
            if tags_dict.get('year'):
                audio.tags.delall("TYER")
                audio.tags.delall("TDRC")
                audio.tags.add(TDRC(encoding=3, text=tags_dict['year']))
            if tags_dict.get('track'):
                audio.tags.delall("TRCK")
                audio.tags.add(TRCK(encoding=3, text=tags_dict['track']))
            if tags_dict.get('comment'):
                audio.tags.delall("COMM")
                audio.tags.add(COMM(encoding=3, lang='eng', desc='', text=tags_dict['comment']))
            if tags_dict.get('lyrics'):
                audio.tags.delall("USLT")
                audio.tags.add(USLT(encoding=3, lang='eng', desc='', text=tags_dict['lyrics']))
            
            audio.save(v2_version=3)
            del audio 
            return True

        elif file_path.lower().endswith(".flac") or file_path.lower().endswith(".ogg"):
            if file_path.lower().endswith(".flac"):
                audio = FLAC(file_path)
            else:
                audio = File(file_path)
                if not isinstance(audio, (OggOpus, OggVorbis)):
                    return False
            
            if tags_dict.get('title'): audio['title'] = tags_dict['title']
            if tags_dict.get('artist'): audio['artist'] = tags_dict['artist']
            if tags_dict.get('album'): audio['album'] = tags_dict['album']
            if tags_dict.get('genre'): audio['genre'] = tags_dict['genre']
            if tags_dict.get('year'): audio['date'] = tags_dict['year']
            if tags_dict.get('track'): audio['tracknumber'] = tags_dict['track']
            if tags_dict.get('lyrics'): audio['lyrics'] = tags_dict['lyrics']
            if tags_dict.get('comment'): audio['description'] = tags_dict['comment']
            
            audio.save()
            del audio
            return True
            
        return False

    except Exception as e:
        print(f"Error applying tags: {e}")
        return False



def get_tags(file_path):
    
    tags_data = {
        "title": "Unknown Title", "artist": "Unknown Artist", "album": "Unknown Album",
        "genre": "Unknown Genre", "year": "----", "track": "0",
        "lyrics": "", "comment": "", "has_cover": False,
        "duration": "0:00", "size": "0 MB" 
    }

    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return tags_data

    audio = None
    try:
        file_size = os.path.getsize(file_path) / (1024 * 1024) 
        tags_data["size"] = f"{file_size:.2f} MB"

        audio = File(file_path)
        
        if audio is None:
            return tags_data

        if audio.info:
            length = int(audio.info.length)
            mins, secs = divmod(length, 60)
            tags_data["duration"] = f"{mins}:{secs:02d}"

        
        if isinstance(audio, MP3) and audio.tags is not None:
            t = audio.tags
            def get_id3(key): return str(t.get(key, "")).strip()
            
            tags_data["title"] = get_id3("TIT2") or "Unknown Title"
            tags_data["artist"] = get_id3("TPE1") or "Unknown Artist"
            tags_data["album"] = get_id3("TALB")
            tags_data["genre"] = get_id3("TCON")
            tags_data["year"] = get_id3("TYER") or get_id3("TDRC")
            tags_data["track"] = get_id3("TRCK")
            
            for k in list(t.keys()):
                if k.startswith("USLT"): tags_data["lyrics"] = str(t[k]).strip(); break
            for k in list(t.keys()):
                if k.startswith("COMM"): 
                    val = str(t[k]).strip()
                    if len(val) > 1 and "eng" not in val: tags_data["comment"] = val; break
            for k in list(t.keys()):
                if k.startswith("APIC"): tags_data["has_cover"] = True; break

        elif isinstance(audio, (FLAC, OggOpus, OggVorbis)):
            def get_vorbis(key): return audio.get(key, [""])[0].strip()
            tags_data["title"] = get_vorbis("title") or "Unknown Title"
            tags_data["artist"] = get_vorbis("artist") or "Unknown Artist"
            tags_data["album"] = get_vorbis("album")
            tags_data["genre"] = get_vorbis("genre")
            tags_data["year"] = get_vorbis("date")
            tags_data["track"] = get_vorbis("tracknumber")
            tags_data["lyrics"] = get_vorbis("lyrics")
            tags_data["comment"] = get_vorbis("comment") or get_vorbis("description")
            if isinstance(audio, FLAC) and audio.pictures:
                tags_data["has_cover"] = True
            elif isinstance(audio, (OggOpus, OggVorbis)) and audio.get("metadata_block_picture"):
                tags_data["has_cover"] = True

    except Exception as e:
        print(f"Error reading tags: {e}")
    
    finally:
        if audio:
            del audio
            
    return tags_data


def set_tag(file_path, tag_type, value):
    if not file_path.lower().endswith(".mp3"):
        return False

    audio = None
    try:
        audio = MP3(file_path, ID3=ID3)
        if audio.tags is None: audio.add_tags()
        tags = audio.tags
        value = str(value).strip()

        if tag_type == 'title':
            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=value))
        elif tag_type == 'artist':
            tags.delall("TPE1")
            tags.add(TPE1(encoding=3, text=value))
        elif tag_type == 'album':
            tags.delall("TALB")
            tags.add(TALB(encoding=3, text=value))
        elif tag_type == 'genre':
            tags.delall("TCON")
            tags.add(TCON(encoding=3, text=value))
        elif tag_type == 'year':
            tags.delall("TYER")
            tags.delall("TDRC")
            tags.add(TDRC(encoding=3, text=value))
        elif tag_type == 'track':
            tags.delall("TRCK")
            tags.add(TRCK(encoding=3, text=value))
        elif tag_type == 'comment':
            tags.delall("COMM")
            tags.add(COMM(encoding=3, lang='eng', desc='', text=value))
        elif tag_type == 'lyrics':
            tags.delall("USLT")
            tags.add(USLT(encoding=3, lang='eng', desc='', text=value))
        
        audio.save(v2_version=3)
        return True
    
    except Exception as e:
        print(f"Error setting tag: {e}")
        return False
    
    finally:
        if audio:
            del audio


def set_cover_from_file(mp3_path, cover_path):

    if not mp3_path.lower().endswith(".mp3"): return False
    
    audio = None
    try:
        audio = MP3(mp3_path, ID3=ID3)
        if audio.tags is None: audio.add_tags()
        
        with open(cover_path, 'rb') as f:
            data = f.read()
            
        audio.tags.delall("APIC")
        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=data))
        audio.save(v2_version=3)
        return True
        
    except Exception as e:
        print(f"Error setting cover: {e}")
        return False
        
    finally:
        if audio:
            del audio


def delete_all_tags(file_path):
    audio = None
    try:
        audio = MP3(file_path)
        audio.delete()
        audio.save()
        del audio
        
        tags = ID3()
        tags.save(file_path, v2_version=3)
        return True
    except Exception as e:
        print(f"Error in heavy cleaning: {e}")
        return False
