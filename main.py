import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import psycopg2
from config import BOT_TOKEN, ADMIN_ID, CHAT_ID, DATABASE_URL

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Подключение к базе данных
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# Состояние игры (в памяти, будет синхронизироваться с базой)
game_state = {
    "active_game": None,
    "players": [],
    "bingo_numbers": [],
    "registration_open": False,
    "pinned_message_id": None,
    "vip_users": [],
    "bonus_users": {}
}

# Загрузка данных из базы при старте
def load_data():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS vip_users (user_id BIGINT PRIMARY KEY, username TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS bonus_users (user_id BIGINT PRIMARY KEY, bonus_count INTEGER)")
        cur.execute("SELECT user_id, username FROM vip_users")
        game_state["vip_users"] = [{"user_id": row[0], "username": row[1]} for row in cur.fetchall()]
        cur.execute("SELECT user_id, bonus_count FROM bonus_users")
        game_state["bonus_users"] = {row[0]: row[1] for row in cur.fetchall()]
    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")
    finally:
        cur.close()
        conn.close()

# Сохранение данных в базу
def save_data():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM vip_users")
        for vip in game_state["vip_users"]:
            cur.execute("INSERT INTO vip_users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username",
                       (vip["user_id"], vip["username"]))
        cur.execute("DELETE FROM bonus_users")
        for user_id, count in game_state["bonus_users"].items():
            cur.execute("INSERT INTO bonus_users (user_id, bonus_count) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET bonus_count = EXCLUDED.bonus_count",
                       (user_id, count))
        conn.commit()
    except Exception as e:
        print(f"Ошибка сохранения данных: {e}")
    finally:
        cur.close()
        conn.close()

# Проверка, является ли пользователь админом
def is_admin(user_id):
    print(f"Проверка админа: user_id={user_id}, ADMIN_ID={ADMIN_ID}")
    return user_id in ADMIN_ID

# Проверка, что команда отправлена в нужном чате
def is_valid_chat(chat_id):
    print(f"Проверка чата: chat_id={chat_id}, CHAT_ID={CHAT_ID}")
    return chat_id == CHAT_ID

# Создание инлайн-клавиатуры для выбора игры
def game_selection_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🎲 Бинго", callback_data="bingo"))
    keyboard.add(InlineKeyboardButton("🎰 Рулетка", callback_data="roulette"))
    return keyboard

# Обновление закреплённого сообщения
def update_pinned_message(chat_id):
    if game_state["players"]:
        message_text = "📋 Список игроков:\n\n"
        for idx, entry in enumerate(game_state["players"], 1):
            if game_state["active_game"] == "bingo":
                numbers = " ".join(map(str, entry["numbers"]))
                message_text += f"{idx}. {entry['username']} {numbers}\n"
            else:
                message_text += f"{idx}. {entry['username']}\n"
    else:
        message_text = "📋 Список игроков:\n\n"

    if game_state["pinned_message_id"]:
        try:
            bot.edit_message_text(message_text, chat_id, game_state["pinned_message_id"])
        except:
            pass
    else:
        msg = bot.send_message(chat_id, message_text)
        try:
            bot.pin_chat_message(chat_id, msg.message_id)
            game_state["pinned_message_id"] = msg.message_id
        except:
            pass

# Загрузка данных при старте
load_data()

# Команда /newchat
@bot.message_handler(commands=['newchat'])
def change_chat(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /newchat от user_id={user_id}, chat_id={chat_id}")

    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только пользователи из ADMIN_ID могут менять чат!")
        return

    try:
        new_chat_id = int(message.text.split()[1])
        print(f"Новый CHAT_ID: {new_chat_id}")
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Укажите ID нового чата, например: /newchat -1001234567890")
        return

    # Проверка, совпадает ли новый чат с текущим
    if new_chat_id == CHAT_ID:
        bot.reply_to(message, "⚠ Бот уже работает в этом чате! Укажите другой ID для переноса.")
        return

    # Подтверждение
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Подтвердить", callback_data=f"confirm_{new_chat_id}"))
    keyboard.add(InlineKeyboardButton("Отмена", callback_data="cancel"))
    bot.reply_to(message, f"📢 Вы хотите перенести бота в чат с ID {new_chat_id}. Подтвердите действие.", reply_markup=keyboard)

# Обработка подтверждения
@bot.callback_query_handler(func=lambda call: True)
def handle_confirmation(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    print(f"Callback от user_id={user_id}, chat_id={chat_id}: {call.data}")

    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Только админы могут подтверждать!")
        return

    if call.data.startswith("confirm_"):
        new_chat_id = int(call.data.split("_")[1])
        global CHAT_ID
        old_chat_id = CHAT_ID
        CHAT_ID = new_chat_id

        # Сохранение данных перед переносом
        save_data()

        # Сообщение о переносе
        transfer_message = (
            f"🚚 Бот успешно перенесён из чата {old_chat_id} в чат {new_chat_id}!\n"
            f"👑 Топ VIP-участников: {', '.join(v['username'] for v in game_state['vip_users']) if game_state['vip_users'] else 'пусто'}\n"
            f"ℹ Данные игры сохранены в базе."
        )
        bot.send_message(old_chat_id, transfer_message)
        bot.send_message(new_chat_id, transfer_message)

        # Сброс текущей игры, но сохранение VIP из базы
        game_state["active_game"] = None
        game_state["registration_open"] = False
        game_state["players"] = []
        game_state["bingo_numbers"] = []
        game_state["pinned_message_id"] = None
        game_state["bonus_users"] = {}

        # Перезагрузка данных из базы
        load_data()

        bot.answer_callback_query(call.id, "✅ Перенос завершён!")
    elif call.data == "cancel":
        bot.answer_callback_query(call.id, "❌ Перенос отменён.")
    else:
        bot.answer_callback_query(call.id, "⚠ Неизвестное действие.")

# Команда /game
@bot.message_handler(commands=['game'])
def start_game(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /game от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может запускать игру!")
        return
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return
    if game_state["active_game"]:
        bot.reply_to(message, "⚠ Игра уже запущена! Завершите с /stop или используйте /reset.")
        return
    bot.reply_to(message, "🎮 Выберите игру:", reply_markup=game_selection_keyboard())

# Команда /vip
@bot.message_handler(commands=['vip'])
def set_vip(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /vip от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может назначать VIP!")
        return
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Ответьте на сообщение пользователя, которого хотите сделать VIP!")
        return

    target_user_id = message.reply_to_message.from_user.id
    target_username = f"@{message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name}"
    if any(vip["user_id"] == target_user_id for vip in game_state["vip_users"]):
        bot.reply_to(message, f"❌ {target_username} уже является VIP!")
        return

    game_state["vip_users"].append({"user_id": target_user_id, "username": target_username})
    save_data()  # Сохранение в базу
    bot.reply_to(message, f"👑 {target_username} получил статус VIP!")

# Команда /delvip
@bot.message_handler(commands=['delvip'])
def remove_vip(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /delvip от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может удалять VIP!")
        return
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Ответьте на сообщение пользователя, которого хотите удалить из VIP!")
        return

    target_user_id = message.reply_to_message.from_user.id
    target_username = f"@{message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name}"
    if not any(vip["user_id"] == target_user_id for vip in game_state["vip_users"]):
        bot.reply_to(message, f"❌ {target_username} не является VIP!")
        return

    game_state["vip_users"] = [vip for vip in game_state["vip_users"] if vip["user_id"] != target_user_id]
    save_data()  # Сохранение в базу
    bot.reply_to(message, f"✅ {target_username} больше не VIP.")

# Команда /bonus
@bot.message_handler(commands=['bonus'])
def set_bonus(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /bonus от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может выдавать бонусы!")
        return
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Ответьте на сообщение пользователя, которому хотите дать бонус!")
        return

    target_user_id = message.reply_to_message.from_user.id
    target_username = f"@{message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name}"
    if is_vip(target_user_id):
        bot.reply_to(message, f"❌ {target_username} является VIP и уже имеет эти привилегии!")
        return
    if target_user_id in game_state["bonus_users"]:
        bot.reply_to(message, f"❌ {target_username} уже получил бонус в этой игре!")
        return

    game_state["bonus_users"][target_user_id] = 1  # Даём 1 дополнительную запись
    save_data()  # Сохранение в базу
    bot.reply_to(message, f"🎁 {target_username} получил бонус на эту игру! Может записываться на бинго с 4 цифрами и на рулетку 2 раза.")

# ... (добавь остальные команды из твоего кода)

# Сохранение данных перед остановкой
import atexit
atexit.register(save_data)

# Запуск бота
if __name__ == "__main__":
    print("Бот запущен...")
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Ошибка в polling: {e}")
        save_data()
