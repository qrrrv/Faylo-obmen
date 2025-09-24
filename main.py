import telebot
from telebot import types
import logging
import time
import re
import os
import threading
from flask import Flask, request
from config import Config
from database import init_db, save_file, get_file, increment_download_count, get_user_files, get_global_stats, get_user_stats, format_size, add_to_favorites, get_favorites, check_password, get_notifications, get_unread_notifications_count, clear_all_notifications

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = telebot.TeleBot(Config.BOT_TOKEN)

# Flask app для поддержки порта
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 File Exchange Bot is Running!"

@app.route('/health')
def health():
    return "OK"

@app.route('/ping')
def ping():
    return "pong"

# Вебхук для Telegram
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK'
    return 'Error'

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'your-app-name.onrender.com')}/webhook"
        bot.remove_webhook()
        time.sleep(1)
        result = bot.set_webhook(url=webhook_url)
        return f"Webhook set to {webhook_url}: {result}"
    except Exception as e:
        return f"Error setting webhook: {e}"

def run_flask():
    """Запуск Flask сервера для порта"""
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def run_bot_webhook():
    """Запуск Telegram бота через вебхук"""
    init_db()
    logger.info("База данных инициализирована")
    logger.info("Бот запущен через вебхук!")
    print("🤖 File Exchange Bot запущен через вебхук!")
    
    # Устанавливаем вебхук
    try:
        webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'your-app-name.onrender.com')}/webhook"
        bot.remove_webhook()
        time.sleep(2)
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")

# Словарь для временных данных
user_data = {}

def extract_file_id(text):
    """Извлечение ID файла из текста"""
    match = re.search(r'file_(\d+)', text)
    if match:
        return int(match.group(1))
    return None

def get_media_type(content_type):
    """Определение типа медиа по content_type"""
    if content_type == 'photo':
        return 'photo'
    elif content_type == 'video':
        return 'video'
    elif content_type == 'audio':
        return 'audio'
    elif content_type == 'voice':
        return 'voice'
    elif content_type == 'document':
        return 'document'
    elif content_type == 'animation':
        return 'gif'
    else:
        return 'file'

@bot.message_handler(commands=['start'])
def cmd_start(message):
    """Обработка команды /start с параметром file_id"""
    try:
        text = message.text
        file_id = None
        password = None
        
        # Парсим параметры из ссылки (правильный способ)
        if len(text.split()) > 1:
            params = text.split()[1]  # Берем параметры после /start
            
            # Ищем file_123
            file_match = re.search(r'file_(\d+)', params)
            if file_match:
                file_id = int(file_match.group(1))
            
            # Ищем pwd_пароль
            pwd_match = re.search(r'pwd_([^_\s]+)', params)
            if pwd_match:
                password = pwd_match.group(1)
        
        if file_id:
            # Это запрос на скачивание файла по ссылке
            file_data = get_file(file_id)
            
            if file_data:
                (telegram_file_id, file_name, file_size, uploader_id, 
                 download_count, media_type, description, file_password, 
                 is_protected, uploader_name) = file_data
                
                # Проверяем пароль если требуется
                if is_protected and file_password:
                    if not password:
                        # Запрашиваем пароль
                        user_data[message.chat.id] = {
                            'file_id': file_id,
                            'awaiting_password': True
                        }
                        bot.send_message(
                            message.chat.id,
                            "🔒 Этот файл защищен паролем\n\n"
                            "📝 Введите пароль для доступа:"
                        )
                        return
                    
                    if not check_password(file_id, password):
                        bot.send_message(message.chat.id, "❌ Неверный пароль")
                        return
                
                # Увеличиваем счетчик скачиваний
                downloader_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
                increment_download_count(file_id, file_size, message.from_user.id, downloader_name or f"User_{message.from_user.id}")
                
                size_str = format_size(file_size)
                caption = f"📦 Файл получен!\n\n📝 {file_name}\n📊 {size_str}\n👤 Загрузил: {uploader_name or 'пользователь'}\n📥 Скачан: {download_count + 1} раз\n"
                
                if description:
                    caption += f"📋 Описание: {description}\n\n"
                else:
                    caption += "\n"
                
                caption += f"⚡ Скачано через @{bot.get_me().username}"
                
                # Отправляем файл
                try:
                    if media_type == 'photo':
                        bot.send_photo(message.chat.id, telegram_file_id, caption=caption)
                    elif media_type == 'video':
                        bot.send_video(message.chat.id, telegram_file_id, caption=caption)
                    elif media_type == 'audio':
                        bot.send_audio(message.chat.id, telegram_file_id, caption=caption)
                    elif media_type == 'voice':
                        bot.send_voice(message.chat.id, telegram_file_id, caption=caption)
                    else:
                        bot.send_document(message.chat.id, telegram_file_id, caption=caption)
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                    # Пытаемся отправить как документ если другие методы не работают
                    bot.send_document(message.chat.id, telegram_file_id, caption=caption)
                
                # Кнопки для дальнейших действий
                markup = types.InlineKeyboardMarkup()
                btn_upload = types.InlineKeyboardButton('📤 Загрузить свой файл', callback_data='upload')
                btn_favorite = types.InlineKeyboardButton('⭐ Добавить в избранное', callback_data=f'fav_{file_id}')
                markup.add(btn_upload, btn_favorite)
                
                bot.send_message(message.chat.id, "🎉 Файл успешно скачан!\n\nХотите загрузить свой файл?", reply_markup=markup)
                return
            else:
                bot.send_message(message.chat.id, "❌ Файл не найден или был удален")
                return
        
        # Если нет параметра - показываем приветствие
        show_welcome(message)
        
    except Exception as e:
        logger.error(f"Error in start: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при обработке запроса")

@bot.message_handler(func=lambda message: user_data.get(message.chat.id, {}).get('awaiting_password'))
def handle_password_input(message):
    """Обработка ввода пароля"""
    try:
        user_info = user_data[message.chat.id]
        file_id = user_info['file_id']
        password = message.text
        
        file_data = get_file(file_id)
        if file_data and check_password(file_id, password):
            del user_data[message.chat.id]
            
            (telegram_file_id, file_name, file_size, uploader_id, 
             download_count, media_type, description, file_password, 
             is_protected, uploader_name) = file_data
            
            downloader_name = f"{message.from_user.first_name or ''} {message.from_user.last_name or ''}".strip()
            increment_download_count(file_id, file_size, message.from_user.id, downloader_name)
            
            size_str = format_size(file_size)
            caption = f"📦 Файл получен!\n\n📝 {file_name}\n📊 {size_str}\n👤 Загрузил: {uploader_name or 'пользователь'}"
            
            try:
                if media_type == 'photo':
                    bot.send_photo(message.chat.id, telegram_file_id, caption=caption)
                elif media_type == 'video':
                    bot.send_video(message.chat.id, telegram_file_id, caption=caption)
                elif media_type == 'audio':
                    bot.send_audio(message.chat.id, telegram_file_id, caption=caption)
                elif media_type == 'voice':
                    bot.send_voice(message.chat.id, telegram_file_id, caption=caption)
                else:
                    bot.send_document(message.chat.id, telegram_file_id, caption=caption)
            except Exception as e:
                logger.error(f"Error sending file: {e}")
                bot.send_document(message.chat.id, telegram_file_id, caption=caption)
                
        else:
            bot.send_message(message.chat.id, "❌ Неверный пароль. Попробуйте еще раз:")
            
    except Exception as e:
        logger.error(f"Error handling password: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при обработке пароля")
        if message.chat.id in user_data:
            del user_data[message.chat.id]

def show_welcome(message):
    """Показать приветственное сообщение"""
    try:
        unread_count = get_unread_notifications_count(message.from_user.id)
        notification_badge = f" 🔔 {unread_count}" if unread_count > 0 else ""
        
        welcome_text = "👋 Добро пожаловать в File Exchange Bot!\n\n🤖 Мгновенный обмен файлами через Telegram\n\n⚡ Просто отправьте мне файл чтобы начать!"
        
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn_upload = types.KeyboardButton('📤 Загрузить файл')
        btn_my_files = types.KeyboardButton('📁 Мои файлы')
        btn_favorites = types.KeyboardButton('⭐ Избранное')
        btn_stats = types.KeyboardButton('📊 Статистика')
        btn_notifications = types.KeyboardButton(f'🔔 Уведомления{notification_badge}')
        btn_help = types.KeyboardButton('❓ Помощь')
        markup.add(btn_upload, btn_my_files, btn_favorites, btn_stats, btn_notifications, btn_help)
        
        bot.send_message(message.chat.id, welcome_text, reply_markup=markup)
    except Exception as e:
        logger.error(f"Error in show_welcome: {e}")
        # Упрощенное сообщение если есть ошибки
        bot.send_message(message.chat.id, "👋 Добро пожаловать! Отправьте файл чтобы начать.")

# Обработчики кнопок
@bot.message_handler(func=lambda message: message.text == '📤 Загрузить файл')
def handle_upload_button(message):
    handle_upload(message)

@bot.message_handler(func=lambda message: message.text == '📁 Мои файлы')
def handle_my_files_button(message):
    handle_my_files(message)

@bot.message_handler(func=lambda message: message.text == '⭐ Избранное')
def handle_favorites_button(message):
    handle_favorites(message)

@bot.message_handler(func=lambda message: message.text == '📊 Статистика')
def handle_stats_button(message):
    handle_stats(message)

@bot.message_handler(func=lambda message: message.text.startswith('🔔 Уведомления'))
def handle_notifications_button(message):
    handle_notifications(message)

@bot.message_handler(func=lambda message: message.text == '❓ Помощь')
def handle_help_button(message):
    handle_help(message)

@bot.message_handler(commands=['upload'])
def handle_upload(message):
    bot.send_message(message.chat.id, "📤 Отправьте мне файл для создания ссылки")

@bot.message_handler(content_types=['photo', 'video', 'audio', 'voice', 'document', 'animation'])
def handle_media(message):
    try:
        user_id = message.from_user.id
        media_type = get_media_type(message.content_type)
        
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
            file_name = f"photo_{int(time.time())}.jpg"
            file_size = message.photo[-1].file_size
        elif message.content_type == 'video':
            file_id = message.video.file_id
            file_name = message.video.file_name or f"video_{int(time.time())}.mp4"
            file_size = message.video.file_size
        elif message.content_type == 'audio':
            file_id = message.audio.file_id
            file_name = message.audio.file_name or f"audio_{int(time.time())}.mp3"
            file_size = message.audio.file_size
        elif message.content_type == 'voice':
            file_id = message.voice.file_id
            file_name = f"voice_{int(time.time())}.ogg"
            file_size = message.voice.file_size
        elif message.content_type == 'document':
            file_id = message.document.file_id
            file_name = message.document.file_name or f"document_{int(time.time())}.bin"
            file_size = message.document.file_size
        elif message.content_type == 'animation':
            file_id = message.animation.file_id
            file_name = f"gif_{int(time.time())}.mp4"
            file_size = message.animation.file_size
        else:
            bot.send_message(message.chat.id, "❌ Неподдерживаемый тип файла")
            return
        
        user_data[user_id] = {
            'file_id': file_id,
            'file_name': file_name,
            'file_size': file_size,
            'media_type': media_type,
            'step': 'description'
        }
        
        bot.send_message(message.chat.id, "📝 Хотите добавить описание к файлу?\n\nОтправьте описание или /skip чтобы пропустить")
        
    except Exception as e:
        logger.error(f"Error handling media: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при обработке файла")

@bot.message_handler(commands=['skip'])
def skip_description(message):
    user_id = message.from_user.id
    if user_id in user_data:
        if user_data[user_id]['step'] == 'description':
            user_data[user_id]['step'] = 'password'
            user_data[user_id]['description'] = None
            bot.send_message(message.chat.id, "🔒 Хотите установить пароль на файл?\n\nОтправьте пароль или /skip чтобы пропустить")
        elif user_data[user_id]['step'] == 'password':
            create_file_link(message, user_data[user_id], None, None)
            del user_data[user_id]

@bot.message_handler(func=lambda message: message.from_user.id in user_data)
def handle_file_setup(message):
    try:
        user_id = message.from_user.id
        user_info = user_data[user_id]
        
        if user_info['step'] == 'description':
            user_info['description'] = message.text
            user_info['step'] = 'password'
            bot.send_message(message.chat.id, "🔒 Хотите установить пароль на файл?\n\nОтправьте пароль или /skip чтобы пропустить")
        elif user_info['step'] == 'password':
            create_file_link(message, user_info, user_info.get('description'), message.text)
            del user_data[user_id]
            
    except Exception as e:
        logger.error(f"Error in file setup: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при настройке файла")
        if user_id in user_data:
            del user_data[user_id]

def create_file_link(message, file_info, description=None, password=None):
    try:
        file_id = save_file(
            file_info['file_id'], 
            file_info['file_name'], 
            file_info['file_size'],
            file_info['media_type'],
            file_info['media_type'],
            message.from_user.id,
            description,
            password
        )
        
        bot_username = bot.get_me().username
        file_link = f"https://t.me/{bot_username}?start=file_{file_id}"
        
        if password:
            file_link += f"&pwd_{password}"
        
        size_str = format_size(file_info['file_size'])
        emoji = "📷" if file_info['media_type'] == 'photo' else "🎥" if file_info['media_type'] == 'video' else "🎵" if file_info['media_type'] == 'audio' else "🎤" if file_info['media_type'] == 'voice' else "📄" if file_info['media_type'] == 'document' else "📁"
        
        success_text = f"{emoji} Ссылка создана!\n\n📝 {file_info['file_name']}\n📊 {size_str}\n👤 Загрузил: {message.from_user.first_name}\n"
        
        if description:
            success_text += f"📋 Описание: {description}\n"
        if password:
            success_text += f"🔒 Защищено паролем\n\n"
        else:
            success_text += "\n"
        
        success_text += f"🔗 Ваша ссылка:\n{file_link}\n\n"
        
        if password:
            success_text += f"🔑 Пароль: {password}\n\n"
        
        success_text += f"📤 Просто перешлите эту ссылку другу!\n\n"
        success_text += f"💡 При переходе файл скачается автоматически"
        
        markup = types.InlineKeyboardMarkup()
        btn_share = types.InlineKeyboardButton('📤 Поделиться', url=f"tg://msg?text={file_link}")
        btn_add_fav = types.InlineKeyboardButton('⭐ В избранное', callback_data=f'fav_{file_id}')
        markup.add(btn_share, btn_add_fav)
        
        bot.send_message(message.chat.id, success_text, reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error creating link: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при создании ссылки")

@bot.message_handler(commands=['myfiles'])
def handle_my_files(message):
    try:
        user_files = get_user_files(message.from_user.id)
        
        if user_files:
            files_text = "📁 Ваши последние файлы:\n\n"
            
            for file_id, file_name, file_size, download_count, upload_date, media_type, is_protected in user_files[:10]:  # Ограничиваем количество
                size_str = format_size(file_size)
                bot_username = bot.get_me().username
                file_link = f"https://t.me/{bot_username}?start=file_{file_id}"
                
                emoji = "📷" if media_type == 'photo' else "🎥" if media_type == 'video' else "🎵" if media_type == 'audio' else "🎤" if media_type == 'voice' else "📄" if media_type == 'document' else "📁"
                lock_emoji = " 🔒" if is_protected else ""
                
                files_text += f"{emoji}{lock_emoji} {file_name}\n📊 {size_str} | 📥 {download_count} скачиваний\n🔗 {file_link}\n────────────────────\n"
            
            bot.send_message(message.chat.id, files_text)
        else:
            bot.send_message(message.chat.id, "📭 У вас еще нет загруженных файлов")
            
    except Exception as e:
        logger.error(f"Error in myfiles: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при получении файлов")

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    try:
        global_stats = get_global_stats()
        user_stats = get_user_stats(message.from_user.id)
        
        stats_text = "🌐 Общая статистика:\n\n"
        stats_text += f"👥 Пользователей: {global_stats['total_users']}\n"
        stats_text += f"📁 Файлов: {global_stats['total_files']}\n"
        stats_text += f"📥 Скачиваний: {global_stats['total_downloads']}\n"
        stats_text += f"📊 Загружено: {format_size(global_stats['total_upload_size'])}\n"
        stats_text += f"📥 Скачано: {format_size(global_stats['total_download_size'])}\n\n"
        
        if user_stats:
            stats_text += "👤 Ваша статистика:\n\n"
            stats_text += f"📤 Загружено файлов: {user_stats['uploads']}\n"
            stats_text += f"📥 Скачано файлов: {user_stats['downloads']}\n"
            stats_text += f"📊 Объем загрузок: {format_size(user_stats['upload_size'])}\n"
            stats_text += f"📥 Объем скачиваний: {format_size(user_stats['download_size'])}\n"
        
        bot.send_message(message.chat.id, stats_text)
        
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при получении статистики")

@bot.message_handler(commands=['favorites'])
def handle_favorites(message):
    try:
        favorites = get_favorites(message.from_user.id)
        
        if favorites:
            fav_text = "⭐ Ваше избранное:\n\n"
            
            for file_id, file_name, file_size, media_type in favorites[:10]:  # Ограничиваем количество
                size_str = format_size(file_size)
                bot_username = bot.get_me().username
                file_link = f"https://t.me/{bot_username}?start=file_{file_id}"
                
                emoji = "📷" if media_type == 'photo' else "🎥" if media_type == 'video' else "🎵" if media_type == 'audio' else "🎤" if media_type == 'voice' else "📄" if media_type == 'document' else "📁"
                
                fav_text += f"{emoji} {file_name}\n📊 {size_str}\n🔗 {file_link}\n────────────────────\n"
            
            bot.send_message(message.chat.id, fav_text)
        else:
            bot.send_message(message.chat.id, "⭐ У вас пока нет избранных файлов")
            
    except Exception as e:
        logger.error(f"Error in favorites: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при получении избранного")

@bot.message_handler(commands=['notifications'])
def handle_notifications(message):
    try:
        notifications = get_notifications(message.from_user.id)
        
        if notifications:
            notif_text = "🔔 Последние уведомления:\n\n"
            
            for notif_id, file_name, downloader_name, download_date, is_read in notifications[:10]:  # Ограничиваем количество
                time_ago = "недавно" if isinstance(download_date, (int, float)) else str(download_date)
                status = "✅" if is_read else "🆕"
                
                notif_text += f"{status} {file_name}\n👤 Скачал: {downloader_name}\n⏰ {time_ago}\n────────────────────\n"
            
            markup = types.InlineKeyboardMarkup()
            btn_clear = types.InlineKeyboardButton('🗑 Очистить все', callback_data='clear_notif')
            markup.add(btn_clear)
            
            bot.send_message(message.chat.id, notif_text, reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "🔔 У вас пока нет уведомлений")
            
    except Exception as e:
        logger.error(f"Error in notifications: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при получении уведомлений")

@bot.message_handler(commands=['help'])
def handle_help(message):
    help_text = (
        "🤖 File Exchange Bot - Помощь\n\n"
        "⚡ Как использовать:\n"
        "1. Отправьте файл боту\n"
        "2. Получите ссылку\n"
        "3. Перешлите ссылку другу\n"
        "4. Друг получает файл!\n\n"
        "📋 Команды:\n"
        "/upload - Загрузить файл\n"
        "/myfiles - Мои файлы\n"
        "/favorites - Избранное\n"
        "/stats - Статистика\n"
        "/notifications - Уведомления\n"
        "/help - Помощь"
    )
    
    bot.send_message(message.chat.id, help_text)

@bot.callback_query_handler(func=lambda call: call.data.startswith('fav_'))
def handle_favorite_callback(call):
    try:
        file_id = int(call.data[4:])
        add_to_favorites(call.from_user.id, file_id)
        bot.answer_callback_query(call.id, "✅ Добавлено в избранное!")
    except Exception as e:
        logger.error(f"Error in favorite callback: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'clear_notif')
def handle_clear_notifications(call):
    try:
        clear_all_notifications(call.from_user.id)
        bot.answer_callback_query(call.id, "✅ Уведомления очищены")
        bot.edit_message_text("🔔 Уведомления очищены", call.message.chat.id, call.message.message_id)
    except Exception as e:
        logger.error(f"Error clearing notifications: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def handle_upload_callback(call):
    try:
        handle_upload(call.message)
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Error in upload callback: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if (not message.text.startswith('/') and 
        message.text not in ['📤 Загрузить файл', '📁 Мои файлы', '⭐ Избранное', '📊 Статистика', '🔔 Уведомления', '❓ Помощь']):
        
        file_id = extract_file_id(message.text)
        if file_id:
            cmd_start(message)
            return
        
        bot.send_message(message.chat.id, "🤖 Отправьте мне файл чтобы получить ссылку!")

if __name__ == "__main__":
    # Инициализация базы данных
    init_db()
    logger.info("База данных инициализирована")
    
    # Запускаем Flask (вебхук будет обрабатываться автоматически)
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Starting bot on port {port}")
    
    # Устанавливаем вебхук при запуске
    try:
        webhook_url = f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'your-app-name.onrender.com')}/webhook"
        bot.remove_webhook()
        time.sleep(2)
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook установлен: {webhook_url}")
    except Exception as e:
        logger.error(f"Error setting webhook: {e}")
    
    # Запускаем Flask app
    app.run(host='0.0.0.0', port=port, debug=False)
