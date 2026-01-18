import json
import os
import psycopg2
from datetime import datetime

def handler(event: dict, context) -> dict:
    '''Telegram бот для звонков с управлением контактами и историей'''
    
    method = event.get('httpMethod', 'POST')
    
    if method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': '',
            'isBase64Encoded': False
        }
    
    if method != 'POST':
        return {
            'statusCode': 405,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Method not allowed'}),
            'isBase64Encoded': False
        }
    
    # Получаем обновление от Telegram (это JSON-строка в теле запроса)
    body = event.get('body', '{}')
    
    # В тестах body это строка с экранированными кавычками
    # При реальном вызове это будет обычная JSON-строка
    try:
        if isinstance(body, str):
            # Убираем лишние кавычки если есть
            clean_body = body.strip('"').replace('\\"', '"')
            update = json.loads(clean_body) if clean_body and clean_body != '{}' else {}
        else:
            update = body if isinstance(body, dict) else {}
    except Exception as e:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Invalid JSON: {str(e)}'}),
            'isBase64Encoded': False
        }
    
    # Проверка что update это словарь
    if not isinstance(update, dict):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Update must be dict, got {type(update).__name__}'}),
            'isBase64Encoded': False
        }
    
    # Подключение к БД
    db_url = os.environ.get('DATABASE_URL')
    schema = os.environ.get('MAIN_DB_SCHEMA')
    
    conn = psycopg2.connect(db_url, options=f'-c search_path={schema}')
    conn.autocommit = True
    cur = conn.cursor()
    
    # Обработка сообщения
    message = update.get('message', {})
    callback_query = update.get('callback_query', {})
    
    if message:
        response_text = handle_message(cur, message)
        chat_id = message.get('chat', {}).get('id')
        keyboard = get_main_keyboard()
    elif callback_query:
        response_text, keyboard = handle_callback(cur, callback_query)
        chat_id = callback_query.get('message', {}).get('chat', {}).get('id')
    else:
        cur.close()
        conn.close()
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'ok': True}),
            'isBase64Encoded': False
        }
    
    cur.close()
    conn.close()
    
    # Отправляем ответ через Telegram API
    telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'method': 'sendMessage',
            'chat_id': chat_id,
            'text': response_text,
            'reply_markup': keyboard
        }),
        'isBase64Encoded': False
    }


def handle_message(cur, message):
    '''Обработка текстовых сообщений'''
    telegram_id = message.get('from', {}).get('id')
    username = message.get('from', {}).get('username')
    first_name = message.get('from', {}).get('first_name', '')
    last_name = message.get('from', {}).get('last_name', '')
    text = message.get('text', '')
    
    # Регистрация/обновление пользователя
    cur.execute(
        "INSERT INTO users (telegram_id, username, first_name, last_name) "
        "VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (telegram_id) DO UPDATE SET username = %s, first_name = %s, last_name = %s",
        (telegram_id, username, first_name, last_name, username, first_name, last_name)
    )
    
    if text == '/start':
        return f"👋 Привет, {first_name}!\n\n📞 Я помогу тебе совершать звонки через Telegram.\n\nВыбери действие:"
    
    elif text.startswith('/add'):
        # Добавление контакта: /add Имя +79991234567
        parts = text.split(' ', 2)
        if len(parts) == 3:
            name = parts[1]
            phone = parts[2]
            
            cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
            user = cur.fetchone()
            user_id = user[0]
            
            cur.execute(
                "INSERT INTO contacts (user_id, name, phone_number) VALUES (%s, %s, %s)",
                (user_id, name, phone)
            )
            return f"✅ Контакт {name} ({phone}) добавлен!"
        else:
            return "❌ Используй формат: /add Имя +79991234567"
    
    else:
        return "❓ Неизвестная команда. Используй кнопки меню."


def handle_callback(cur, callback_query):
    '''Обработка нажатий на кнопки'''
    telegram_id = callback_query.get('from', {}).get('id')
    data = callback_query.get('data', '')
    
    cur.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
    user = cur.fetchone()
    if not user:
        return "❌ Ошибка: пользователь не найден", get_main_keyboard()
    
    user_id = user[0]
    
    if data == 'contacts':
        cur.execute(
            "SELECT id, name, phone_number, is_favorite FROM contacts WHERE user_id = %s ORDER BY is_favorite DESC, name",
            (user_id,)
        )
        contacts = cur.fetchall()
        
        if not contacts:
            return "📇 У тебя пока нет контактов.\n\nДобавь контакт командой:\n/add Имя +79991234567", get_main_keyboard()
        
        text = "📇 Твои контакты:\n\n"
        buttons = []
        for contact in contacts:
            star = "⭐ " if contact[3] else ""
            text += f"{star}{contact[1]} - {contact[2]}\n"
            buttons.append([{
                'text': f"📞 {contact[1]}",
                'callback_data': f"call_{contact[0]}"
            }])
        
        buttons.append([{'text': '◀️ Назад', 'callback_data': 'main'}])
        return text, {'inline_keyboard': buttons}
    
    elif data == 'history':
        cur.execute(
            "SELECT phone_number, call_status, call_duration, created_at FROM call_history "
            "WHERE user_id = %s ORDER BY created_at DESC LIMIT 10",
            (user_id,)
        )
        history = cur.fetchall()
        
        if not history:
            return "📋 История звонков пуста", get_main_keyboard()
        
        text = "📋 История звонков:\n\n"
        for call in history:
            status_emoji = "✅" if call[1] == "completed" else "❌" if call[1] == "failed" else "⏸️"
            date = call[3].strftime("%d.%m.%Y %H:%M")
            duration = f"{call[2]}с" if call[2] > 0 else "-"
            text += f"{status_emoji} {call[0]} ({duration}) - {date}\n"
        
        return text, get_main_keyboard()
    
    elif data == 'favorites':
        cur.execute(
            "SELECT id, name, phone_number FROM contacts WHERE user_id = %s AND is_favorite = TRUE ORDER BY name",
            (user_id,)
        )
        favorites = cur.fetchall()
        
        if not favorites:
            return "⭐ У тебя нет избранных контактов", get_main_keyboard()
        
        text = "⭐ Избранные контакты:\n\n"
        buttons = []
        for fav in favorites:
            text += f"{fav[1]} - {fav[2]}\n"
            buttons.append([{
                'text': f"📞 {fav[1]}",
                'callback_data': f"call_{fav[0]}"
            }])
        
        buttons.append([{'text': '◀️ Назад', 'callback_data': 'main'}])
        return text, {'inline_keyboard': buttons}
    
    elif data.startswith('call_'):
        contact_id = int(data.split('_')[1])
        
        cur.execute(
            "SELECT name, phone_number FROM contacts WHERE id = %s AND user_id = %s",
            (contact_id, user_id)
        )
        contact = cur.fetchone()
        
        if not contact:
            return "❌ Контакт не найден", get_main_keyboard()
        
        buttons = [
            [{'text': '✅ Подтвердить звонок', 'callback_data': f'confirm_{contact_id}'}],
            [{'text': '❌ Отмена', 'callback_data': 'contacts'}]
        ]
        
        return f"📞 Позвонить на номер {contact[1]} ({contact[0]})?", {'inline_keyboard': buttons}
    
    elif data.startswith('confirm_'):
        contact_id = int(data.split('_')[1])
        
        cur.execute(
            "SELECT name, phone_number FROM contacts WHERE id = %s AND user_id = %s",
            (contact_id, user_id)
        )
        contact = cur.fetchone()
        
        if not contact:
            return "❌ Контакт не найден", get_main_keyboard()
        
        # Записываем звонок в историю
        cur.execute(
            "INSERT INTO call_history (user_id, contact_id, phone_number, call_status) VALUES (%s, %s, %s, %s)",
            (user_id, contact_id, contact[1], 'initiated')
        )
        
        return f"📞 Звоним на {contact[1]}...\n\n⚠️ Функция звонков требует Telegram Premium и API доступа", get_main_keyboard()
    
    elif data == 'main':
        return "Главное меню:", get_main_keyboard()
    
    return "❓ Неизвестное действие", get_main_keyboard()


def get_main_keyboard():
    '''Главное меню бота'''
    return {
        'inline_keyboard': [
            [{'text': '📇 Контакты', 'callback_data': 'contacts'}],
            [{'text': '⭐ Избранное', 'callback_data': 'favorites'}],
            [{'text': '📋 История', 'callback_data': 'history'}]
        ]
    }