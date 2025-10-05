import os
import json
from flask import Flask, request, jsonify
import openai
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# --- 1. ИНИЦИАЛИЗАЦИЯ И НАСТРОЙКА ---

app = Flask(__name__)

# Загрузка базы знаний со сценариями
try:
    with open('knowledge_base.json', 'r', encoding='utf-8') as f:
        knowledge_base = json.load(f)
    app.logger.info("База знаний 'knowledge_base.json' успешно загружена.")
except Exception as e:
    app.logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось загрузить knowledge_base.json: {e}")
    knowledge_base = {}

# Валидация и загрузка переменных окружения
REQUIRED_VARS = [
    "OPENAI_API_KEY", "WAHA_API_ENDPOINT", "WAHA_SESSION_ID",
    "GOOGLE_SHEET_URL", "SERVICE_ACCOUNT_KEY_JSON"
]
missing_vars = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing_vars:
    raise RuntimeError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
WAHA_API_ENDPOINT = os.environ["WAHA_API_ENDPOINT"]
WAHA_SESSION_ID = os.environ["WAHA_SESSION_ID"]
GOOGLE_SHEET_URL = os.environ["GOOGLE_SHEET_URL"]
SERVICE_ACCOUNT_KEY_JSON = os.environ["SERVICE_ACCOUNT_KEY_JSON"]

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Подключение к Google Sheets
try:
    # Создаем словарь с ключом из переменной окружения
    key_dict = json.loads(SERVICE_ACCOUNT_KEY_JSON)
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    gspread_client = gspread.authorize(creds)
    
    products_sheet = gspread_client.open_by_url(GOOGLE_SHEET_URL).worksheet("products")
    customers_sheet = gspread_client.open_by_url(GOOGLE_SHEET_URL).worksheet("customers")
    app.logger.info("Успешное подключение к Google Таблице (листы products и customers).")
except Exception as e:
    app.logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Google Таблице: {e}")
    products_sheet, customers_sheet = None, None

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_all_products_from_sheet():
    """Загружает все товары из Google Таблицы."""
    if not products_sheet:
        app.logger.error("Нет подключения к Google Таблице, поиск товаров невозможен.")
        return pd.DataFrame()
    try:
        all_records = products_sheet.get_all_records()
        df = pd.DataFrame(all_records)
        if 'SKU' in df.columns:
            df['SKU'] = df['SKU'].astype(str)
        return df
    except Exception as e:
        app.logger.error(f"Ошибка при чтении данных из Google Таблицы: {e}")
        return pd.DataFrame()

def check_availability_and_get_stock(product_row):
    """Проверяет наличие товара по колонкам PP1-PP5 и возвращает общее количество."""
    stock_count = 0
    is_available = False
    for i in range(1, 6):
        stock_value = str(product_row.get(f'PP{i}', 'no')).lower().strip()
        if stock_value != 'no' and stock_value.isdigit():
            count = int(stock_value)
            if count > 0:
                is_available = True
                stock_count += count
    
    if is_available:
        return stock_count
    return 0

def update_customer_data(customer_info, order_info):
    """Находит клиента в таблице customers, обновляет или создает его."""
    if not customers_sheet:
        app.logger.error("Нет подключения к листу 'customers'.")
        return
    
    try:
        phone = str(customer_info['phone'])
        cell = customers_sheet.find(phone, in_column=1) # Ищем телефон в первой колонке (A)
        
        current_stage = "POST_PURCHASE"

        if cell: # Если клиент найден, обновляем
            row_index = cell.row
            old_history_str = customers_sheet.cell(row_index, 4).value or '[]'
            try:
                order_history = json.loads(old_history_str)
            except json.JSONDecodeError:
                order_history = []
            order_history.append(order_info)
            
            customers_sheet.update_cell(row_index, 2, customer_info.get('name', ''))
            customers_sheet.update_cell(row_index, 3, current_stage)
            customers_sheet.update_cell(row_index, 4, json.dumps(order_history, ensure_ascii=False))
            app.logger.info(f"Обновлены данные для клиента {phone}")
        else: # Если клиент не найден, создаем новую строку
            new_row = [
                phone,
                customer_info.get('name', ''),
                current_stage,
                json.dumps([order_info], ensure_ascii=False)
            ]
            customers_sheet.append_row(new_row)
            app.logger.info(f"Создана новая запись для клиента {phone}")
    except Exception as e:
        app.logger.error(f"Ошибка при обновлении данных клиента в Google Таблице: {e}")

def send_waha_message(phone, text):
    """Отправляет сообщение через WhatsApp HTTP API (WAHA)."""
    url = f"{WAHA_API_ENDPOINT.rstrip('/')}/api/v1/sessions/{WAHA_SESSION_ID}/messages/text"
    payload = {"chatId": f"{phone}@c.us", "text": text}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        app.logger.info("WAHA message sent to %s", phone)
        return True
    except requests.exceptions.RequestException as e:
        app.logger.error("WAHA send error: %s", e)
        return False

def get_openai_response(prompt, model="gpt-4o"):
    """Получает ответ от OpenAI."""
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Ты — продвинутый ИИ-ассистент по продажам. Твоя задача — строго следовать инструкциям и генерировать готовый ответ для клиента."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"OpenAI API error: {e}")
        return "Приносим извинения, произошла техническая ошибка."

def build_prompt_from_kb(stage_id, context):
    """Создает 'супер-промпт' для OpenAI на основе базы знаний."""
    scenario = knowledge_base.get("scenarios", {}).get(stage_id)
    if not scenario:
        return f"Ошибка: Сценарий для этапа '{stage_id}' не найден в базе знаний."

    prompt_parts = [
        "ТЫ — ИИ-продажник. Сгенерируй ответ для клиента, строго следуя приведенным ниже инструкциям.",
        f"\n--- СЦЕНАРИЙ: {scenario.get('description', 'Без описания')} ---",
        "Твои действия и фразы должны быть основаны на этом скрипте:",
        "\n".join(f"- {line}" for line in scenario.get("script", [])),
        "\n--- ОБЩИЕ ПРАВИЛА КОММУНИКАЦИИ ---",
        "Всегда придерживайся этих правил:",
        "\n".join(f"- {rule}" for rule in knowledge_base.get("rules", {}).get("general", [])),
        "\n--- КОНТЕКСТ ДИАЛОГА ---",
        "Вот информация о текущей ситуации:",
        "\n".join(f"- {key}: {value}" for key, value in context.items()),
        "\n--- ТВОЯ ЗАДАЧА ---",
        "Сгенерируй ОДНО готовое сообщение для отправки клиенту. Не задавай уточняющих вопросов мне, а сразу пиши финальный текст."
    ]
    return "\n".join(prompt_parts)

# --- 3. ЛОГИКА ДЛЯ ЭТАПОВ ВОРОНКИ ---

def handle_upsell_logic(data):
    """Обрабатывает логику допродажи после покупки."""
    customer_info = data.get("customer", {})
    order_info = data.get("order", {})
    phone = customer_info.get("phone")
    if not phone:
        return jsonify({"status": "error", "message": "Missing customer phone"}), 400

    # Обновляем/создаем запись о клиенте в Google Таблице
    update_customer_data(customer_info, order_info)

    # Логика допродажи на основе категории товара
    purchased_sku = order_info.get('sku')
    if purchased_sku:
        all_products_df = get_all_products_from_sheet()
        if not all_products_df.empty:
            purchased_product = all_products_df[all_products_df['SKU'] == str(purchased_sku)]
            
            if not purchased_product.empty:
                category = purchased_product.iloc[0].get('category')
                
                if category:
                    same_category_products = all_products_df[
                        (all_products_df['category'] == category) &
                        (all_products_df['SKU'] != str(purchased_sku))
                    ]

                    recommended_products = []
                    # Проверяем наличие и отбираем до 5 товаров
                    for index, row in same_category_products.head(5).iterrows():
                        stock = check_availability_and_get_stock(row)
                        if stock > 0:
                            product_info = row.to_dict()
                            product_info['total_stock'] = stock
                            recommended_products.append(product_info)
                    
                    if recommended_products:
                        # Формируем текст с рекомендациями (не более 3-х)
                        recommendations_text = ""
                        for prod in recommended_products[:3]:
                            recommendations_text += f"\n- {prod['model']} (Цена: {prod['price']} KZT"
                            if prod['total_stock'] <= 3:
                                recommendations_text += f", осталось всего {prod['total_stock']} шт.!"
                            recommendations_text += ")"
                        
                        context = {"Клиент": customer_info.get('name'), "Купленный товар": order_info.get('product_name'), "Рекомендации": recommendations_text}
                        prompt = build_prompt_from_kb("after_purchase_upsell", context)
                        
                        ai_message = get_openai_response(prompt)
                        send_waha_message(phone, ai_message)
                        return jsonify({"status": "success", "action": "upsell_sent"})

    # Если допродажа не сработала, отправляем простое сообщение благодарности
    send_waha_message(phone, f"Здравствуйте, {customer_info.get('name')}! Спасибо за ваш заказ. В ближайшее время мы приступим к его обработке.")
    return jsonify({"status": "success", "action": "simple_thank_you_sent"})

# --- 4. ГЛАВНЫЙ ДИСПЕТЧЕР И ЭНДПОИНТЫ ---

@app.route("/")
def index():
    """Простой эндпоинт для проверки, что сервис работает."""
    return "AI Sales Agent is running!", 200

@app.route("/event_handler", methods=["POST"])
def event_handler():
    event_data = request.get_json(force=True, silent=True)
    if not event_data:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400
    
    stage = event_data.get("waha_stage_id")
    if not stage:
        return jsonify({"status": "error", "message": "Отсутствует waha_stage_id"}), 400

    # Упрощенная логика без отложенных задач
    if stage == "POST_PURCHASE":
        return handle_upsell_logic(event_data)
    # Здесь можно добавить обработку других этапов (например, для запроса отзыва)
    # elif stage == "ORDER_DELIVERED":
    #     return handle_review_logic(event_data)
    else:
        return jsonify({"status": "info", "message": f"Этап '{stage}' получен, но обработчик не реализован."}), 200

if __name__ == "__main__":
    # Эта часть нужна для локального тестирования
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

