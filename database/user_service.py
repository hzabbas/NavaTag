import sqlite3

DB_PATH = 'bot_database.db'

def _execute(query, params=(), fetch=False, fetchall=False):
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        if fetch:
            return cursor.fetchone()
        if fetchall:
            return cursor.fetchall()
        conn.commit()
        return cursor.rowcount

def initialize_database():
    with sqlite3.connect(DB_PATH, timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, 
                username TEXT, 
                full_name TEXT, 
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS locked_channels (
                channel_id TEXT PRIMARY KEY, 
                title TEXT, 
                invite_link TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, 
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS user_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                user_id INTEGER, 
                channel_id TEXT, 
                channel_title TEXT, 
                is_selected INTEGER DEFAULT 1, 
                UNIQUE(user_id, channel_id)
            );
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY, 
                fast_mode INTEGER DEFAULT 0,
                custom_caption TEXT DEFAULT NULL,
                key TEXT,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS user_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                user_id INTEGER, 
                tag_name TEXT, 
                tag_value TEXT, 
                UNIQUE(user_id, tag_name)
            );
        ''')
       
        try:
            cursor.execute('ALTER TABLE user_settings ADD COLUMN custom_caption TEXT DEFAULT NULL;')
        except sqlite3.OperationalError:
            pass 
        conn.commit()

def set_fast_mode(user_id, status):
    _execute('''
        INSERT INTO user_settings (user_id, fast_mode) 
        VALUES (?, ?) 
        ON CONFLICT(user_id) DO UPDATE SET fast_mode=excluded.fast_mode
    ''', (user_id, int(status)))

def get_fast_mode(user_id):
    res = _execute('SELECT fast_mode FROM user_settings WHERE user_id = ?', (user_id,), fetch=True)
    return res[0] == 1 if res else False

def set_custom_caption(user_id, caption):
    if caption is None or caption.strip() == "0":
        _execute('''
            INSERT INTO user_settings (user_id, custom_caption) 
            VALUES (?, NULL) 
            ON CONFLICT(user_id) DO UPDATE SET custom_caption=NULL
        ''', (user_id,))
    else:
        _execute('''
            INSERT INTO user_settings (user_id, custom_caption) 
            VALUES (?, ?) 
            ON CONFLICT(user_id) DO UPDATE SET custom_caption=excluded.custom_caption
        ''', (user_id, caption.strip()))

def get_custom_caption(user_id):
    res = _execute('SELECT custom_caption FROM user_settings WHERE user_id = ?', (user_id,), fetch=True)
    return res[0] if res and res[0] else None

def set_user_preset(user_id, tag_name, tag_value):
    _execute('INSERT OR REPLACE INTO user_presets (user_id, tag_name, tag_value) VALUES (?, ?, ?)', (user_id, tag_name, tag_value))

def delete_user_preset(user_id, tag_name):
    _execute('DELETE FROM user_presets WHERE user_id = ? AND tag_name = ?', (user_id, tag_name))

def get_user_presets(user_id):
    rows = _execute('SELECT tag_name, tag_value FROM user_presets WHERE user_id = ?', (user_id,), fetchall=True)
    return {row[0]: row[1] for row in rows} if rows else {}

def add_locked_channel(channel_id, title, invite_link):
    try:
        _execute('INSERT OR REPLACE INTO locked_channels (channel_id, title, invite_link) VALUES (?, ?, ?)', (str(channel_id), title, invite_link))
        return True
    except Exception:
        return False

def remove_locked_channel(channel_id):
    _execute('DELETE FROM locked_channels WHERE channel_id = ?', (str(channel_id),))

def get_locked_channels():
    return _execute('SELECT channel_id, title, invite_link FROM locked_channels', fetchall=True) or []

def set_bot_setting(key, value):
    _execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))

def get_bot_setting(key):
    res = _execute('SELECT value FROM settings WHERE key = ?', (key,), fetch=True)
    return res[0] if res else None

def add_user(user_id, username, full_name):
    try:
        _execute('''
            INSERT INTO users (user_id, username, full_name) 
            VALUES (?, ?, ?) 
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name
        ''', (user_id, username, full_name))
    except Exception:
        pass

def get_total_users_count():
    try:
        res = _execute('SELECT COUNT(*) FROM users', fetch=True)
        return res[0] if res else 0
    except Exception:
        return 0

def get_all_users_id():
    try:
        rows = _execute('SELECT user_id FROM users', fetchall=True)
        return [row[0] for row in rows] if rows else []
    except Exception:
        return []

def add_channel(user_id, channel_id, title):
    try:
        _execute('INSERT OR IGNORE INTO user_channels (user_id, channel_id, channel_title, is_selected) VALUES (?, ?, ?, 1)', (user_id, str(channel_id), title))
        return True
    except Exception:
        return False

def get_user_channels(user_id):
    return _execute('SELECT channel_id, channel_title, is_selected FROM user_channels WHERE user_id = ?', (user_id,), fetchall=True) or []

def toggle_channel_selection(user_id, channel_id):
    res = _execute('SELECT is_selected FROM user_channels WHERE user_id = ? AND channel_id = ?', (user_id, str(channel_id)), fetch=True)
    if res:
        new_status = 0 if res[0] == 1 else 1
        _execute('UPDATE user_channels SET is_selected = ? WHERE user_id = ? AND channel_id = ?', (new_status, user_id, str(channel_id)))

def delete_channel(user_id, channel_id):
    _execute('DELETE FROM user_channels WHERE user_id = ? AND channel_id = ?', (user_id, str(channel_id)))

def get_selected_channels(user_id):
    rows = _execute('SELECT channel_id FROM user_channels WHERE user_id = ? AND is_selected = 1', (user_id,), fetchall=True)
    return [row[0] for row in rows] if rows else []

def set_user_setting(user_id, key, value):
    _execute('''
        INSERT INTO user_settings (user_id, key, value) 
        VALUES (?, ?, ?) 
        ON CONFLICT(user_id) DO UPDATE SET key=excluded.key, value=excluded.value
    ''', (user_id, key, str(value)))

def has_language_set(user_id):
    res = _execute('SELECT value FROM user_settings WHERE user_id = ? AND key = ?', (user_id, 'language'), fetch=True)
    return bool(res)

def get_user_language(user_id):
    res = _execute('SELECT value FROM user_settings WHERE user_id = ? AND key = ?', (user_id, 'language'), fetch=True)
    return res[0] if res else 'fa'