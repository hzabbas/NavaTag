import sqlite3

def add_channel(user_id, channel_id, title):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO user_channels (user_id, channel_id, channel_title, is_selected)
            VALUES (?, ?, ?, 1)
        ''', (user_id, str(channel_id), title))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

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