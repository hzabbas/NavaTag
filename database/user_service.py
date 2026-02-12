import sqlite3

def initialize_database():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locked_channels (
            channel_id TEXT PRIMARY KEY,
            title TEXT,
            invite_link TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id TEXT,
            channel_title TEXT,
            is_selected INTEGER DEFAULT 1,
            UNIQUE(user_id, channel_id)
        )
    ''')

 
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            fast_mode INTEGER DEFAULT 0
        )
    ''')


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            tag_name TEXT,
            tag_value TEXT,
            UNIQUE(user_id, tag_name)
        )
    ''')
    
    conn.commit()
    conn.close()


def set_fast_mode(user_id, status):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO user_settings (user_id, fast_mode) VALUES (?, ?)', (user_id, int(status)))
        conn.commit()
    finally: conn.close()

def get_fast_mode(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT fast_mode FROM user_settings WHERE user_id = ?', (user_id,))
        res = cursor.fetchone()
        return res[0] == 1 if res else False
    finally: conn.close()

def set_user_preset(user_id, tag_name, tag_value):
    """ذخیره یک تگ ثابت برای کاربر"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO user_presets (user_id, tag_name, tag_value) VALUES (?, ?, ?)', (user_id, tag_name, tag_value))
        conn.commit()
    finally: conn.close()

def delete_user_preset(user_id, tag_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM user_presets WHERE user_id = ? AND tag_name = ?', (user_id, tag_name))
        conn.commit()
    finally: conn.close()

def get_user_presets(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT tag_name, tag_value FROM user_presets WHERE user_id = ?', (user_id,))
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows}
    finally: conn.close()

# --- بقیه توابع قبلی (بدون تغییر) ---
def add_locked_channel(channel_id, title, invite_link):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO locked_channels (channel_id, title, invite_link) VALUES (?, ?, ?)', (str(channel_id), title, invite_link))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def remove_locked_channel(channel_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM locked_channels WHERE channel_id = ?', (str(channel_id),))
        conn.commit()
    finally: conn.close()

def get_locked_channels():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT channel_id, title, invite_link FROM locked_channels')
        return cursor.fetchall()
    finally: conn.close()

def set_bot_setting(key, value):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        conn.commit()
    finally: conn.close()

def get_bot_setting(key):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        res = cursor.fetchone()
        return res[0] if res else None
    finally: conn.close()

def add_user(user_id, username, full_name):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR REPLACE INTO users (user_id, username, full_name) VALUES (?, ?, ?)', (user_id, username, full_name))
        conn.commit()
    except: pass
    finally: conn.close()

def get_total_users_count():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT COUNT(*) FROM users')
        return cursor.fetchone()[0]
    except: return 0
    finally: conn.close()

def get_all_users_id():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT user_id FROM users')
        return [row[0] for row in cursor.fetchall()]
    except: return []
    finally: conn.close()

def add_channel(user_id, channel_id, title):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR IGNORE INTO user_channels (user_id, channel_id, channel_title, is_selected) VALUES (?, ?, ?, 1)', (user_id, str(channel_id), title))
        conn.commit()
        return True
    except: return False
    finally: conn.close()

def get_user_channels(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id, channel_title, is_selected FROM user_channels WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows 

def toggle_channel_selection(user_id, channel_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_selected FROM user_channels WHERE user_id = ? AND channel_id = ?', (user_id, str(channel_id)))
    result = cursor.fetchone()
    if result:
        new_status = 0 if result[0] == 1 else 1
        cursor.execute('UPDATE user_channels SET is_selected = ? WHERE user_id = ? AND channel_id = ?', (new_status, user_id, str(channel_id)))
        conn.commit()
    conn.close()

def delete_channel(user_id, channel_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_channels WHERE user_id = ? AND channel_id = ?', (user_id, str(channel_id)))
    conn.commit()
    conn.close()

def get_selected_channels(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id FROM user_channels WHERE user_id = ? AND is_selected = 1', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def set_user_setting(user_id, key, value):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO user_settings (user_id, key, value) VALUES (?, ?, ?)', 
                  (user_id, key, str(value)))
    conn.commit()
    conn.close()