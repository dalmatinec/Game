import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import random
import sqlite3
from config import BOT_TOKEN, ADMIN_ID, CHAT_IDS, DATABASE_URL  # Исправлено, убрано дублирование

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Состояние игры
game_state = {
    "active_game": None,  # "bingo" или "roulette"
    "players": [],  # Список записей: {"user_id": user_id, "username": username, "numbers": numbers}
    "bingo_numbers": [],  # Выбранные числа для Бинго
    "registration_open": False,
    "pinned_message_id": None,
    "vip_users": [],  # Список словарей: {"user_id": user_id, "username": username}
    "bonus_users": {}  # {user_id: количество_доп_записей}
}

# Проверка, что команда отправлена в нужном чате
def is_valid_chat(chat_id):
    print(f"Проверка чата: chat_id={chat_id}, CHAT_IDS={CHAT_IDS}")
    return chat_id in CHAT_IDS

# Подключение к базе данных SQLite
def get_db_connection():
    return sqlite3.connect(DATABASE_URL)

# Загрузка данных из базы при старте
def load_data():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vip_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bonus_users (
                user_id INTEGER PRIMARY KEY,
                bonus_count INTEGER
            )
        """)
        # Загружаем VIP-пользователей
        cur.execute("SELECT user_id, username FROM vip_users")
        game_state["vip_users"] = []
        rows = cur.fetchall()
        for row in rows:
            game_state["vip_users"].append({"user_id": row[0], "username": row[1]})
        # Загружаем бонусных пользователей
        cur.execute("SELECT user_id, bonus_count FROM bonus_users")
        game_state["bonus_users"] = {}
        rows = cur.fetchall()
        for row in rows:
            game_state["bonus_users"][row[0]] = row[1]
        conn.commit()
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
            cur.execute("INSERT OR REPLACE INTO vip_users (user_id, username) VALUES (?, ?)",
                        (vip["user_id"], vip["username"]))
        cur.execute("DELETE FROM bonus_users")
        for user_id, count in game_state["bonus_users"].items():
            cur.execute("INSERT OR REPLACE INTO bonus_users (user_id, bonus_count) VALUES (?, ?)",
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
def is_valid_chat(chat_id):  # Убери эту дублирующуюся функцию, оставь только первую
    print(f"Проверка чата: chat_id={chat_id}, CHAT_IDS={CHAT_IDS}")
    return chat_id in CHAT_IDS

# Проверка, является ли пользователь VIP
def is_vip(user_id):
    for vip in game_state["vip_users"]:
        if vip["user_id"] == user_id:
            return True
    return False

# Подсчёт количества записей пользователя
def count_entries(user_id):
    count = 0
    for entry in game_state["players"]:
        if entry["user_id"] == user_id:
            count += 1
    return count

# Создание инлайн-клавиатуры для выбора игры
def game_selection_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🎲 Бинго", callback_data="bingo"))
    keyboard.add(InlineKeyboardButton("🎰 Рулетка", callback_data="roulette"))
    return keyboard

# Создание инлайн-клавиатуры для записи
def register_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📝 Записаться", callback_data="register"))
    return keyboard

# Обновление закреплённого сообщения
def update_pinned_message(chat_id):
    message_text = "📋 Список игроков:\n\n"
    if game_state["players"]:
        for idx, entry in enumerate(game_state["players"], 1):
            if game_state["active_game"] == "bingo":
                numbers = " ".join(map(str, entry["numbers"]))
                message_text += f"{idx}. {entry['username']} {numbers}\n"
            else:
                message_text += f"{idx}. {entry['username']}\n"

    keyboard = register_button() if game_state["active_game"] == "roulette" and game_state["registration_open"] else None

    if game_state["pinned_message_id"]:
        try:
            bot.edit_message_text(message_text, chat_id, game_state["pinned_message_id"], reply_markup=keyboard)
        except:
            pass
    else:
        msg = bot.send_message(chat_id, message_text, reply_markup=keyboard)
        try:
            bot.pin_chat_message(chat_id, msg.message_id)
            game_state["pinned_message_id"] = msg.message_id
        except:
            pass

# Загрузка данных при старте
load_data()

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

# Обработка выбора игры и регистрации
@bot.callback_query_handler(func=lambda call: True)
def handle_game_selection(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    print(f"Callback от user_id={user_id}, chat_id={chat_id}: {call.data}")

    # Обработка кнопки "Записаться"
    if call.data == "register":
        if not is_valid_chat(chat_id):
            bot.answer_callback_query(call.id, "❌ Этот бот работает только в указанном чате!")
            return
        if game_state["active_game"] != "roulette" or not game_state["registration_open"]:
            bot.answer_callback_query(call.id, "❌ Регистрация на рулетку не открыта!")
            return
        
        username = f"@{call.from_user.username or call.from_user.first_name}"
        current_entries = count_entries(user_id)
        max_entries = 2 if is_vip(user_id) else (1 + game_state["bonus_users"].get(user_id, 0))
        if current_entries >= max_entries:
            bot.answer_callback_query(call.id, f"❌ Вы уже записаны максимальное количество раз ({max_entries})!")
            return
        
        game_state["players"].append({"user_id": user_id, "username": username})
        update_pinned_message(chat_id)
        bot.answer_callback_query(call.id, "✅ Вы записаны!")
        return

    # Обработка выбора игры (только для админов)
    if not is_admin(user_id):
        bot.answer_callback_query(call.id, "❌ Только админ может выбирать игру!")
        return

    game_state["active_game"] = call.data
    game_state["registration_open"] = True
    game_state["players"] = []
    game_state["bingo_numbers"] = []
    game_state["pinned_message_id"] = None

    if call.data == "bingo":
        bot.send_message(chat_id, 
                        "🎲 Запись на Бинго открыта!\n📝 Для участия отправьте @ и 5 чисел от 1 до 100 (или 4 для VIP/бонус)\nПример: @ 1 2 3 4 5\n\n📋 Список игроков:")
        update_pinned_message(chat_id)
    elif call.data == "roulette":
        bot.send_message(chat_id, 
                        "🎰 Запись на Рулетку открыта!\n📝 Для участия отправьте @\n\n📋 Список игроков:")
        update_pinned_message(chat_id)

    bot.answer_callback_query(call.id)

# Регистрация игроков
@bot.message_handler(regexp=r'^@')
def register_player(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = f"@{message.from_user.username or message.from_user.first_name}"
    print(f"Регистрация игрока: {username}, user_id={user_id}, chat_id={chat_id}")
    if not game_state["registration_open"]:
        return
    if not is_valid_chat(chat_id):
        return

    current_entries = count_entries(user_id)
    max_entries = 2 if is_vip(user_id) else (1 + game_state["bonus_users"].get(user_id, 0))

    if current_entries >= max_entries:
        bot.reply_to(message, f"❌ Вы уже записаны максимальное количество раз ({max_entries})!")
        return

    if game_state["active_game"] == "bingo":
        parts = message.text.strip().split()
        if parts[0] == "@":
            # Формат: @ 1 2 3 4 5
            required_numbers = 4 if (is_vip(user_id) or user_id in game_state["bonus_users"]) else 5
            if len(parts) != required_numbers + 1:
                bot.reply_to(message, f"❌ Ожидается {required_numbers} чисел! Пример: @ 1 2 3 4{' 5' if required_numbers == 5 else ''}")
                return
            username_to_save = username  # Используем username отправителя
        else:
            # Формат: @username 1 2 3 4 5
            required_numbers = 4 if (is_vip(user_id) or user_id in game_state["bonus_users"]) else 5
            if len(parts) != required_numbers + 2:  # +2, т.к. есть @username и числа
                bot.reply_to(message, f"❌ Ожидается {required_numbers} чисел после @username! Пример: @username 1 2 3 4{' 5' if required_numbers == 5 else ''}")
                return
            username_to_save = parts[0]  # Используем указанный @username
            parts = parts[1:]  # Убираем @username из списка для обработки чисел

        try:
            numbers = [int(x) for x in parts]
            # Проверка на дубликаты
            if len(set(numbers)) != len(numbers):
                bot.reply_to(message, "❌ Цифры повторяются! Выберите уникальные числа.")
                return
            # Проверка диапазона чисел
            for x in numbers:
                if x < 1 or x > 100:
                    bot.reply_to(message, "❌ Числа должны быть от 1 до 100!")
                    return
        except ValueError:
            bot.reply_to(message, "❌ Все числа должны быть целыми!")
            return

        game_state["players"].append({"user_id": user_id, "username": username_to_save, "numbers": numbers})
        update_pinned_message(chat_id)

    elif game_state["active_game"] == "roulette":
        if message.text.strip() != "@":
            return
        
        game_state["players"].append({"user_id": user_id, "username": username})
        update_pinned_message(chat_id)

# Команда /spisok
@bot.message_handler(commands=['spisok'])
def stop_registration(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /spisok от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может завершать сбор!")
        return
    if not is_valid_chat(chat_id):
        return
    if not game_state["registration_open"]:
        bot.reply_to(message, "⚠ Сбор игроков уже завершён или не начат!")
        return
    game_state["registration_open"] = False
    bot.send_message(chat_id, f"⏹ Сбор игроков завершён!\n🎮 Игра {game_state['active_game'].title()} начинается! Всем удачи! 🍀")
    update_pinned_message(chat_id)  # Убираем кнопку "Записаться"

# Команды /num и /num2
@bot.message_handler(commands=['num', 'num2'])
def generate_bingo_numbers(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда {message.text} от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может генерировать числа!")
        return
    if not is_valid_chat(chat_id):
        return
    if game_state["active_game"] != "bingo" or game_state["registration_open"]:
        bot.reply_to(message, "⚠ Игра Бинго не активна или сбор не завершён!")
        return
    count = 1 if message.text == "/num" else 2
    new_rows = []
    for _ in range(count):
        row = random.sample(range(1, 101), 5)
        new_rows.append(row)
    for row in new_rows:
        game_state["bingo_numbers"].append(row)
    message_text = ""
    for row in game_state["bingo_numbers"]:
        message_text += " | ".join(map(str, row)) + "\n➖\n"
    bot.send_message(chat_id, message_text)

# Проверка слова "Бинго"
@bot.message_handler(func=lambda message: message.text.lower().strip() in ["bingo", "бинго"])
def check_bingo(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = f"@{message.from_user.username or message.from_user.first_name}"
    print(f"Проверка Бинго от {username}, user_id={user_id}, chat_id={chat_id}")
    if game_state["active_game"] != "bingo" or game_state["registration_open"]:
        return
    if not is_valid_chat(chat_id):
        return

    user_entries = []
    for entry in game_state["players"]:
        if entry["user_id"] == user_id:
            user_entries.append(entry)
    if not user_entries:
        bot.reply_to(message, "❌ Вы не участвуете в игре!")
        return

    bingo_numbers = set()
    for row in game_state["bingo_numbers"]:
        for num in row:
            bingo_numbers.add(num)
    for entry in user_entries:
        player_numbers = set()
        for num in entry["numbers"]:
            player_numbers.add(num)
        if player_numbers.issubset(bingo_numbers):
            bot.send_message(chat_id, 
                            f"✅ {username} заявил Бинго! Числа совпадают! Админ, проверьте остальные условия. 🎉")
            return

    bot.send_message(chat_id, 
                    f"❌ {username}, не обманывайте! Не все ваши числа есть в списке. Админ, продолжайте игру! 😡")

# Команда /random
@bot.message_handler(commands=['random'])
def random_roulette(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /random от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может запускать рандом!")
        return
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return
    if game_state["active_game"] != "roulette" or game_state["registration_open"]:
        bot.reply_to(message, "⚠ Игра Рулетка не активна или сбор не завершён!")
        return
    try:
        count = int(message.text.split()[1])
        if count != len(game_state["players"]):
            bot.reply_to(message, f"❌ Указано неверное количество игроков! В списке: {len(game_state['players'])}")
            return
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Укажите число игроков, например /random 30")
        return
    random_index = random.randint(1, count)
    bot.send_message(chat_id, f"🎰 Рандом: {random_index}\n⏳ Ждём 1 минуту...")

# Команда /stop
@bot.message_handler(commands=['stop'])
def stop_game(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /stop от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может завершить игру!")
        return
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return
    if not game_state["active_game"]:
        bot.reply_to(message, "⚠ Игра не запущена!")
        return
    bot.send_message(chat_id, f"🏁 Игра {game_state['active_game'].title()} завершена! Всем спасибо за участие! 🎉")
    game_state["active_game"] = None
    game_state["registration_open"] = False
    game_state["players"] = []
    game_state["bingo_numbers"] = []
    game_state["pinned_message_id"] = None
    game_state["bonus_users"] = {}

# Команда /reset
@bot.message_handler(commands=['reset'])
def reset_game(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    print(f"Команда /reset от user_id={user_id}, chat_id={chat_id}")
    if not is_admin(user_id):
        bot.reply_to(message, "❌ Только админ может сбросить игру!")
        return
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return
    bot.send_message(chat_id, "🔄 Состояние игры сброшено! Теперь можно начать новую игру с /game.")
    game_state["active_game"] = None
    game_state["registration_open"] = False
    game_state["players"] = []
    game_state["bingo_numbers"] = []
    game_state["pinned_message_id"] = None

# Команда /getid
@bot.message_handler(commands=['getid'])
def get_id(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    username = f"@{message.from_user.username or message.from_user.first_name}"
    print(f"Команда /getid от user_id={user_id}, chat_id={chat_id}")
    bot.reply_to(message, f"📋 Информация:\n"
                          f"- Ваш ID: {user_id}\n"
                          f"- ID чата: {chat_id}\n"
                          f"- Ваше имя: {username}")

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
    for vip in game_state["vip_users"]:
        if vip["user_id"] == target_user_id:
            bot.reply_to(message, f"❌ {target_username} уже является VIP!")
            return

    game_state["vip_users"].append({"user_id": target_user_id, "username": target_username})
    save_data()
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
    found = False
    for vip in game_state["vip_users"]:
        if vip["user_id"] == target_user_id:
            found = True
            break
    if not found:
        bot.reply_to(message, f"❌ {target_username} не является VIP!")
        return

    new_vip_users = []
    for vip in game_state["vip_users"]:
        if vip["user_id"] != target_user_id:
            new_vip_users.append(vip)
    game_state["vip_users"] = new_vip_users
    save_data()
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

    game_state["bonus_users"][target_user_id] = 1
    save_data()
    bot.reply_to(message, f"🎁 {target_username} получил бонус на эту игру! Может быть записан на бинго с 4 цифрами и на рулетку 2 раза.")

# Команда /top
@bot.message_handler(commands=['top'])
def show_top(message):
    chat_id = message.chat.id
    print(f"Команда /top от user_id={message.from_user.id}, chat_id={chat_id}")
    if not is_valid_chat(chat_id):
        bot.reply_to(message, "❌ Этот бот работает только в указанном чате!")
        return

    if not game_state["vip_users"]:
        bot.send_message(chat_id, "👑 Топ VIP-участников:\n\nСписок пустой!")
        return

    message_text = "👑 Топ VIP-участников:\n\n"
    for idx, vip in enumerate(game_state["vip_users"], 1):
        message_text += f"{idx}. {vip['username']}\n"
    bot.send_message(chat_id, message_text)

# Команда /help
@bot.message_handler(commands=['help'])
def help_command(message):
    chat_id = message.chat.id
    print(f"Команда /help от user_id={message.from_user.id}, chat_id={chat_id}")
    help_text = (
        "📖 Список команд бота:\n\n"
        "🎮 /game — Запустить новую игру (Бинго или Рулетка).\n"
        "📋 /spisok — Завершить сбор игроков и начать игру.\n"
        "🔢 /num — Выдать 1 ряд из 5 случайных чисел (для Бинго).\n"
        "🔢 /num2 — Выдать 2 ряда из 5 случайных чисел (для Бинго).\n"
        "🔗 /bingo — Сообщить, что у вас есть все числа (для Бинго).\n"
        "🎰 /random <число> — Выбрать случайный номер (для Рулетки, например /random 30).\n"
        "🏁 /stop — Завершить игру (Бинго или Рулетка). Бонусы сбрасываются.\n"
        "🔄 /reset — Принудительно сбросить состояние игры.\n"
        "📋 /getid — Показать ваш ID и ID чата.\n"
        "👑 /vip — Назначить участника VIP (для админов).\n"
        "👑 /delvip — Удалить участника из VIP (для админов).\n"
        "🎁 /bonus — Дать бонус участнику (для админов).\n"
        "🏆 /top — Показать список VIP-участников.\n"
        "📖 /help — Показать это сообщение.\n\n"
        "❗ Примечания:\n"
        "- Для участия в Бинге отправьте @ и 5 чисел (или 4 для VIP/бонуса) (например, @ 1 2 3 4 5).\n"
        "- Для участия в Рулетке отправьте @ или нажмите кнопку 'Записаться' в закреплённом сообщении.\n"
        "- Команды /game, /spisok, /num, /num2, /random, /stop, /reset, /vip, /delvip, /bonus доступны только админу."
    )
    bot.send_message(chat_id, help_text)

# Сохранение данных перед завершением
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
