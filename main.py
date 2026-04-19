import os
import json
import datetime
import google.generativeai as genai
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# --- Конфигурация ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = 'credentials.json'

EXPECTED_HEADERS = ["Дата", "Время", "Продукт / Активность", "Примерный вес", "Калории", "Белки", "Жиры", "Углеводы", "Сумма за день", "Совет от ИИ"]

if not GEMINI_API_KEY or not SPREADSHEET_ID:
    print("ОШИБКА: Не заданы GEMINI_API_KEY или SPREADSHEET_ID в файле .env")
    exit(1)

# Инициализация Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})

# Инициализация Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def get_sheets_service():
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ОШИБКА: Файл {CREDENTIALS_FILE} не найден.")
        exit(1)
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    return build('sheets', 'v4', credentials=creds)

def init_sheet(service, spreadsheet_id):
    try:
        sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        first_sheet_name = sheet_metadata.get('sheets', [])[0].get('properties', {}).get('title', 'Sheet1')
        target_range = f"'{first_sheet_name}'!A1:J1"
    except Exception as e:
        print(f"Ошибка при получении списка листов:\n{e}")
        raise e
    
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=target_range).execute()
    values = result.get('values', [])
    
    if not values or len(values[0]) < len(EXPECTED_HEADERS) or values[0][:len(EXPECTED_HEADERS)] != EXPECTED_HEADERS:
        print(f"Обновляю заголовки на листе '{first_sheet_name}' (добавлены Сумма за день и Совет)...")
        body = {'values': [EXPECTED_HEADERS]}
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=target_range,
            valueInputOption="USER_ENTERED", body=body).execute()
    
    return first_sheet_name

def parse_food_input(text):
    now = datetime.datetime.now()
    prompt = f"""
    Проанализируй текст от пользователя: "{text}"
    
    ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА:
    1. Верни СТРОГО массив JSON.
    2. Разбей перечисленную еду на отдельные объекты.
    3. ВНИМАНИЕ (ПРО БЖУ): ВСЕГДА примерно рассчитывай Белки, Жиры и Углеводы! Никогда не ставь 0 для еды (особенно для макарон, сыра, творога, мороженого). Если точных данных нет, используй средние знания о продукте. Писать 0 можно только для воды и чая без сахара.
    4. СОВЕТ ПО ПИТАНИЮ: Для всего этого приема пищи придумай ОДИН короткий совет/критику (строго 5-6 слов). Например: "Слишком много сахара, добавь белок", "Отличный плотный ужин, молодец", "Сплошные углеводы, где клетчатка?". Продублируй этот один и тот же совет в каждый объект массива.

    Формат JSON:
    [
      {{
        "Дата": "YYYY-MM-DD",
        "Время": "HH:MM",
        "Продукт_или_Активность": "Название",
        "Примерный вес": "В граммах",
        "Калории": "Ккал (число)",
        "Белки": "Граммы (число)",
        "Жиры": "Граммы (число)",
        "Углеводы": "Граммы (число)",
        "Совет": "Твой совет из 5-6 слов"
      }}
    ]
    Справка для текущей даты: {now.strftime("%Y-%m-%d %H:%M")}
    """
    response = model.generate_content(prompt)
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        print("Ошибка ответа ИИ:\n", response.text)
        return []

def append_to_sheet(data, service, target_sheet_name):
    if not data: return
    sheet = service.spreadsheets()
    
    values = []
    for item in data:
        row = [
            item.get("Дата", ""),
            item.get("Время", ""),
            item.get("Продукт_или_Активность", ""),
            item.get("Примерный вес", ""),
            item.get("Калории", ""),
            item.get("Белки", ""),
            item.get("Жиры", ""),
            item.get("Углеводы", ""),
            '=SUMIF(A:A, INDIRECT("A"&ROW()), E:E)', # Хак: Гугл сам сложит все калории за дату в этой строке
            item.get("Совет", "")
        ]
        values.append(row)
        
    try:
        result = sheet.values().append(
            spreadsheetId=SPREADSHEET_ID, range=f"'{target_sheet_name}'!A:J",
            valueInputOption="USER_ENTERED", body={'values': values}).execute()
        updated = result.get('updates', {}).get('updatedCells', 0)
        print(f"Записано {updated} ячеек в таблицу!")
    except Exception as e:
        print(f"Ошибка при записи:\n{e}")

def main():
    print("=== Умный Трекер Калорий (Gemini + Google Sheets) ===")
    try:
        service = get_sheets_service()
        active_sheet_name = init_sheet(service, SPREADSHEET_ID)
    except Exception:
        return

    print("Вводите то, что съели (для выхода введите 'выход'):")
    while True:
        text = input("Ваш лог > ")
        if text.strip().lower() in ['выход', 'exit', 'q']:
            break
        if not text.strip(): continue
            
        parsed_data = parse_food_input(text)
        if parsed_data:
            print("\nРаспознано:")
            for d in parsed_data:
                print(f" - {d.get('Продукт_или_Активность')} | {d.get('Калории')} ккал | БЖУ: {d.get('Белки')}/{d.get('Жиры')}/{d.get('Углеводы')}")
            
            if len(parsed_data) > 0 and parsed_data[0].get('Совет'):
                print(f"> Совет ИИ: {parsed_data[0].get('Совет')}")
                
            append_to_sheet(parsed_data, service, active_sheet_name)
        print("-" * 40)

if __name__ == "__main__":
    main()
