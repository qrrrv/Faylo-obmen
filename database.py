import sqlite3
import time
from config import Config

def init_db():
    """Инициализация базы данных и создание таблиц"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    # Таблица для файлов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            file_type TEXT,
            media_type TEXT,
            user_id INTEGER NOT NULL,
            upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            download_count INTEGER DEFAULT 0,
            total_download_size INTEGER DEFAULT 0,
            description TEXT,
            password TEXT,
            is_protected INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица для статистики пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            total_uploads INTEGER DEFAULT 0,
            total_downloads INTEGER DEFAULT 0,
            total_upload_size INTEGER DEFAULT 0,
            total_download_size INTEGER DEFAULT 0
        )
    ''')
    
    # Таблица для избранных файлов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            file_id INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, file_id)
        )
    ''')
    
    # Таблица для уведомлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id INTEGER NOT NULL,
            downloader_id INTEGER,
            downloader_name TEXT,
            download_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_read INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()

def save_file(file_id, file_name, file_size, file_type, media_type, user_id, description=None, password=None):
    """Сохранение информации о файле в базу данных"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    is_protected = 1 if password else 0
    
    # Сохраняем файл
    cursor.execute(
        '''INSERT INTO files (file_id, file_name, file_size, file_type, media_type, user_id, description, password, is_protected) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (file_id, file_name, file_size, file_type, media_type, user_id, description, password, is_protected)
    )
    
    # Обновляем статистику пользователя
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name) 
        VALUES (?, ?, ?, ?)
    ''', (user_id, '', '', ''))
    
    cursor.execute('''
        UPDATE users 
        SET total_uploads = total_uploads + 1, 
            total_upload_size = total_upload_size + ?
        WHERE user_id = ?
    ''', (file_size, user_id))
    
    conn.commit()
    file_id = cursor.lastrowid
    conn.close()
    return file_id

def get_file(file_id):
    """Получение информации о файле по ID"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT file_id, file_name, file_size, user_id, download_count, 
               media_type, description, password, is_protected,
               (SELECT username FROM users WHERE user_id = files.user_id) as username
        FROM files 
        WHERE id = ?
    ''', (file_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def check_password(file_id, password):
    """Проверка пароля файла"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT password FROM files WHERE id = ?', (file_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result and result[0]:
        return result[0] == password
    return True  # Если пароля нет, доступ разрешен

def increment_download_count(file_id, download_size, downloader_id=None, downloader_name=None):
    """Увеличение счетчика скачиваний и добавление уведомления"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    # Обновляем счетчик скачиваний
    cursor.execute('''
        UPDATE files 
        SET download_count = download_count + 1,
            total_download_size = total_download_size + ?
        WHERE id = ?
    ''', (download_size, file_id))
    
    # Обновляем статистику пользователя (для скачивающего)
    cursor.execute('''
        UPDATE users 
        SET total_downloads = total_downloads + 1,
            total_download_size = total_download_size + ?
        WHERE user_id = (SELECT user_id FROM files WHERE id = ?)
    ''', (download_size, file_id))
    
    # Добавляем уведомление если указан скачивающий
    if downloader_id:
        cursor.execute('''
            INSERT INTO notifications (user_id, file_id, downloader_id, downloader_name)
            VALUES ((SELECT user_id FROM files WHERE id = ?), ?, ?, ?)
        ''', (file_id, file_id, downloader_id, downloader_name))
    
    conn.commit()
    conn.close()

def get_user_files(user_id):
    """Получение файлов пользователя"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, file_name, file_size, download_count, upload_date, media_type, is_protected
        FROM files 
        WHERE user_id = ? 
        ORDER BY upload_date DESC 
        LIMIT 10
    ''', (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_global_stats():
    """Получение глобальной статистики"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    # Общая статистика
    cursor.execute('SELECT COUNT(*) FROM files')
    total_files = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT SUM(file_size) FROM files')
    total_upload_size = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT SUM(total_download_size) FROM files')
    total_download_size = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT SUM(download_count) FROM files')
    total_downloads = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return {
        'total_files': total_files,
        'total_users': total_users,
        'total_upload_size': total_upload_size,
        'total_download_size': total_download_size,
        'total_downloads': total_downloads
    }

def get_user_stats(user_id):
    """Получение статистики пользователя"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT total_uploads, total_downloads, total_upload_size, total_download_size 
        FROM users 
        WHERE user_id = ?
    ''', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return {
            'uploads': result[0],
            'downloads': result[1],
            'upload_size': result[2],
            'download_size': result[3]
        }
    return None

def add_to_favorites(user_id, file_id):
    """Добавление файла в избранное"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO favorites (user_id, file_id) 
        VALUES (?, ?)
    ''', (user_id, file_id))
    conn.commit()
    conn.close()

def get_favorites(user_id):
    """Получение избранных файлов пользователя"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT f.id, f.file_name, f.file_size, f.media_type 
        FROM files f 
        JOIN favorites fav ON f.id = fav.file_id 
        WHERE fav.user_id = ? 
        ORDER BY fav.added_date DESC
    ''', (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_notifications(user_id):
    """Получение уведомлений пользователя"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT n.id, f.file_name, n.downloader_name, n.download_date, n.is_read
        FROM notifications n
        JOIN files f ON n.file_id = f.id
        WHERE n.user_id = ?
        ORDER BY n.download_date DESC
        LIMIT 20
    ''', (user_id,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_unread_notifications_count(user_id):
    """Получение количества непрочитанных уведомлений"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def clear_all_notifications(user_id):
    """Очистка всех уведомлений пользователя"""
    conn = sqlite3.connect(Config.DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM notifications WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def format_size(size_bytes):
    """Форматирование размера файла в читаемый вид"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    size = size_bytes
    while size >= 1024 and i < len(size_names) - 1:
        size /= 1024
        i += 1
    return f"{size:.2f} {size_names[i]}"