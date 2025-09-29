import os
import json
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
import openai
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from apscheduler.schedulers.background import BackgroundScheduler

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

# Обязательные переменные окружения
REQUIRED_VARS = [
    "OPENAI_API_KEY", "WAHA_API_ENDPOINT", "WAHA_SESSION_ID",
    "FUNCTION_URL", "GOOGLE_SHEET_URL"
]
missing_vars = [v for v in REQUIRED_VARS if not os.environ.get(v)]
if missing_vars:
    raise RuntimeError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}")

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
WAHA_API_ENDPOINT = os.environ["WAHA_API_ENDPOINT"]
WAHA_SESSION_ID = os.environ["WAHA_SESSION_ID"]
FUNCTION_URL = os.environ["FUNCTION_URL"]
GOOGLE_SHEET_URL = os.environ["GOOGLE_SHEET_URL"]

# Ключ-файл используется для аутентификации в Google
KEY_PATH = "kaspiseller-57379-firebase-adminsdk-fbsvc-1c22a63a88.json"

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Подключение к Google Sheets
try:
    scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(KEY_PATH, scope)
    gspread_client = gspread.authorize(creds)
    products_sheet = gspread_client.open_by_url(GOOGLE_SHEET_URL).worksheet("products")
    customers_sheet = gspread_client.open_by_url(GOOGLE_SHEET_URL).worksheet("customers")
    app.logger.info("Успешное подключение к Google Таблице (листы products и customers).")
except Exception as e:
    app.logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: Не удалось подключиться к Google Таблице: {e}")
    products_sheet, customers_sheet = None, None

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_all_products_from_sheet():
    if not products_sheet:
        return pd.DataFrame()
    try:
        all_records = products_sheet.get_all_records()
        df = pd.DataFrame(all_records)
        df['SKU'] = df['SKU'].astype(str)
        return df
    except:
        return pd.DataFrame()

def check_availability_and_get_stock(product_row):
    stock_count, is_available = 0, False
    for i in range(1, 6):
        stock_value = str(product_row.get(f'PP{i}', 'no')).lower().strip()
        if stock_value != 'no' and stock_value.isdigit():
            count = int(stock_value)
            if count > 0:
                is_available = True
                stock_count += count
    return stock_count if is_available else 0

def update_customer_in_sheet(customer_info, stage, order_info=None):
    if not customers_sheet:
        return
    try:
        phone = str(customer_info['phone'])
        cell = customers_sheet.find(phone, in_column=1)
        if cell:  # update
            row_index = cell.row
            customers_sheet.update_cell(row_index, 2, customer_info.get('name', ''))
            customers_sheet.update_cell(row_index, 3, stage)
            if order_info:
                old_history_str = customers_sheet.cell(row_index, 4).value or '[]'
                try: order_history = json.loads(old_history_str)
                except: order_history = []
                order_history.append(order_info)
                customers_sheet.update_cell(row_index, 4, json.dumps(order_history, ensure_ascii=False))
        else:  # create new
            new_row = [
                phone, customer_info.get('name', ''), stage,
                json.dumps([order_info] if order_info else [], ensure_ascii=False)
            ]
            customers_sheet.append_row(new_row)
    except Exception as e:
        app.logger.error(f"Ошибка при обновлении данных клиента: {e}")

def send_waha_message(phone, text):
    # WAHA API call
    try:
        url = f"{WAHA_API_ENDPOINT}/api/sendMessage/{WAHA_SESSION_ID}"
        payload = {"phone": phone, "message": text}
        requests.post(url, json=payload)
    except Exception as e:
        app.logger.error(f"Ошибка при отправке WAHA-сообщения: {e}")

def get_openai_response(prompt, model="gpt-4o"):
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": "Ты помощник по продажам."},
                      {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        app.logger.error(f"Ошибка OpenAI: {e}")
        return "Извините, сейчас не могу ответить."

def build_prompt_from_kb(stage_id, context):
    stage = knowledge_base.get("scenarios", {}).get(stage_id, {})
    script = stage.get("script", [])
    text = "\n".join(script)
    for k, v in context.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text

# --- 3. ПЛАНИРОВЩИК (замена Cloud Tasks) ---

scheduler = BackgroundScheduler()
scheduler.start()

def schedule_task(func, payload, delay_seconds=172800):
    run_time = datetime.now() + timedelta(seconds=delay_seconds)
    scheduler.add_job(func, 'date', run_date=run_time, args=[payload])

def process_review_request(payload):
    customer_info = payload.get("customer", {})
    order_info = payload.get("order", {})
    update_customer_in_sheet(customer_info, "NURTURING")
    context = {"Клиент": customer_info.get('name'), "Купленный товар": order_info.get('product_name')}
    prompt = build_prompt_from_kb("delivery_feedback", context)
    ai_message = get_openai_response(prompt)
    send_waha_message(customer_info.get("phone"), ai_message)

# --- 4. ЛОГИКА ДЛЯ ЭТАПОВ ВОРОНКИ ---

def handle_upsell_logic(data):
    customer_info = data.get("customer", {})
    order_info = data.get("order", {})
    phone = customer_info.get("phone")
    if not phone: return jsonify({"status": "error", "message": "Missing customer phone"}), 400

    update_customer_in_sheet(customer_info, "POST_PURCHASE", order_info)

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
                    recommendations_text = ""
                    for _, row in same_category_products.head(3).iterrows():
                        stock = check_availability_and_get_stock(row)
                        if stock > 0:
                            recommendations_text += f"\n- {row['model']} (Цена: {row['price']} KZT)"
                    context = {
                        "Клиент": customer_info.get('name'),
                        "Купленный товар": order_info.get('product_name'),
                        "Рекомендации": recommendations_text
                    }
                    prompt = build_prompt_from_kb("after_purchase_upsell", context)
                    ai_message = get_openai_response(prompt)
                    send_waha_message(phone, ai_message)
                    return jsonify({"status": "success", "action": "upsell_sent"})
    send_waha_message(phone, f"Здравствуйте, {customer_info.get('name')}! Спасибо за ваш заказ.")
    return jsonify({"status": "success", "action": "simple_thank_you_sent"})

def handle_delivered_logic(data):
    customer_info = data.get("customer", {})
    update_customer_in_sheet(customer_info, "ORDER_DELIVERED")
    task_payload = {"task_type": "REVIEW_REQUEST", "customer": customer_info, "order": data.get("order")}
    schedule_task(process_review_request, task_payload)
    return jsonify({"status": "success", "action": "review_request_scheduled"})

# --- 5. РОУТЫ ---

@app.route("/event_handler", methods=["POST"])
def event_handler():
    event_data = request.get_json(force=True, silent=True)
    if not event_data: return jsonify({"status": "error", "message": "Invalid JSON"}), 400
    stage = event_data.get("waha_stage_id")
    if stage == "POST_PURCHASE": return handle_upsell_logic(event_data)
    elif stage == "ORDER_DELIVERED": return handle_delivered_logic(event_data)
    else: return jsonify({"status": "error", "message": f"Неизвестный этап: {stage}"}), 400

@app.route("/")
def healthcheck():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

# --- 6. ЗАПУСК ---

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
