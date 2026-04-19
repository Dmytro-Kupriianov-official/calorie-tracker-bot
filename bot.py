import os
import telebot
from dotenv import load_dotenv

# Имортируем всю нашу готовую логику из main.py
from main import get_sheets_service, init_sheet, parse_food_input, append_to_sheet, SPREADSHEET_ID

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TELEGRAM_TOKEN:
    print("ОШИБКА: Токен Telegram бота не найден в файле .env!")
    print("Откройте файл .env и добавьте строку: TELEGRAM_TOKEN=ваш_токен_от_botfather")
    exit(1)

# Создаем бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Инициализация гугл таблиц прямо при старте бота
try:
    print("Запускаю Telegram-бота... Подключаюсь к Google Sheets...")
    sheets_service = get_sheets_service()
    active_sheet_name = init_sheet(sheets_service, SPREADSHEET_ID)
    print(f"Готово! Бот готов записывать в Гугл Таблицу (лист '{active_sheet_name}').")
except Exception as e:
    print(f"Ошибка при подключении к таблице: {e}")
    exit(1)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Привет, мехатроник! 🦾\nЯ твой личный ИИ-трекер калорий.\n\nПросто напиши сюда всё, что ты сегодня съел (одним сообщением), и я сам всё переварю, посчитаю БЖУ и закину в твою Гугл Таблицу!")

@bot.message_handler(func=lambda message: True)
def process_food_log(message):
    msg = bot.reply_to(message, "⏳ Отправляю лог в ИИ-мозг (Gemini)...")
    
    # 1. Парсим текст от юзера через Gemini
    parsed_data = parse_food_input(message.text)
    
    if not parsed_data:
        bot.edit_message_text("❌ Извини, лог не распознан. Попробуй описать еду по-другому.", chat_id=msg.chat.id, message_id=msg.message_id)
        return
        
    # Формируем красивый отчет для ответа в Телеграм
    report = "✅ **Распознано и добавлено:**\n\n"
    for d in parsed_data:
        report += f"🍔 {d.get('Продукт_или_Активность')}\n"
        report += f"🔥 {d.get('Калории')} ккал | БЖУ: {d.get('Белки')}/{d.get('Жиры')}/{d.get('Углеводы')}\n\n"
        
    if len(parsed_data) > 0 and parsed_data[0].get('Совет'):
        report += f"🤖 **Совет ИИ:** {parsed_data[0].get('Совет')}"
        
    # 2. Обновляем сообщение с результатами парсинга
    bot.edit_message_text(report, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode="Markdown")
    
    # 3. Записываем в Гугл Таблицу
    bot.send_message(message.chat.id, "📝 Дописываю строки в твою Гугл Таблицу...")
    try:
        append_to_sheet(parsed_data, sheets_service, active_sheet_name)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка при записи в таблицу: {e}")

print("🤖 Бот запущен и круглосуточно слушает твои сообщения (нажми Ctrl+C в терминале для остановки)...")
bot.infinity_polling()
