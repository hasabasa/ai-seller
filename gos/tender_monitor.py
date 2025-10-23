# Автор: hasabasa

import time
from datetime import datetime, timedelta
from queue import PriorityQueue
import json
import os
from config import Config

class TenderMonitor:
    def __init__(self, selenium_bot, ncanode_client, config):
        self.bot = selenium_bot
        self.ncanode = ncanode_client
        self.config = config
        self.pending_queue = PriorityQueue()
        self.processed_ids = set()
        self._load_processed_ids()
    
    def _load_processed_ids(self):
        """Загрузить ID обработанных тендеров"""
        processed_file = os.path.join(self.config.OUTPUT_DIR, "processed.json")
        if os.path.exists(processed_file):
            try:
                with open(processed_file, 'r', encoding='utf-8') as f:
                    self.processed_ids = set(json.load(f))
            except:
                self.processed_ids = set()
    
    def _save_processed_ids(self):
        """Сохранить ID обработанных тендеров"""
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        processed_file = os.path.join(self.config.OUTPUT_DIR, "processed.json")
        with open(processed_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.processed_ids), f, ensure_ascii=False, indent=2)
    
    def parse_deadline(self, deadline_str):
        """Парсинг срока подачи заявок"""
        try:
            if not deadline_str:
                return datetime.now()
            
            # Попытка парсинга разных форматов
            formats = [
                "%d.%m.%Y %H:%M",
                "%Y-%m-%d %H:%M",
                "%d.%m.%Y",
                "%Y-%m-%d"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(deadline_str.strip(), fmt)
                except:
                    continue
            
            return datetime.now()
        except:
            return datetime.now()
    
    def monitor_loop(self):
        """Основной цикл мониторинга (синхронный)"""
        print("\n" + "="*80)
        print("ЗАПУСК МОНИТОРИНГА ТЕНДЕРОВ")
        print("="*80 + "\n")
        
        while True:
            try:
                print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Проверка новых тендеров...")
                
                # Переходим к списку тендеров
                self.bot.navigate_to_tenders(self.config.BASE_URL, self.config.CATEGORY)
                
                # Получаем карточки тендеров
                cards = self.bot.get_tender_cards()
                print(f"[→] Найдено карточек на странице: {len(cards)}")
                
                new_count = 0
                now = datetime.now()
                
                for card in cards:
                    tender_data = self.bot.extract_tender_data(card)
                    if not tender_data:
                        continue
                    
                    tender_id = tender_data["link"]
                    
                    # Пропускаем уже обработанные
                    if tender_id in self.processed_ids:
                        continue
                    
                    new_count += 1
                    print(f"\n[!] НОВЫЙ ТЕНДЕР: {tender_data['title'][:60]}...")
                    print(f"    Номер: {tender_data.get('number', 'N/A')}")
                    print(f"    Заказчик: {tender_data.get('customer', 'N/A')}")
                    
                    # Определяем время начала подачи заявок
                    deadline = self.parse_deadline(tender_data.get("deadline"))
                    
                    if deadline <= now:
                        # Можно подавать сейчас
                        print(f"[→] Обработка немедленно")
                        self.process_tender(tender_data)
                    else:
                        # Добавляем в очередь ожидания
                        wait_seconds = (deadline - now).total_seconds()
                        print(f"[→] Отложено до {deadline.strftime('%Y-%m-%d %H:%M:%S')} ({int(wait_seconds)} сек)")
                        self.pending_queue.put((deadline, tender_data))
                    
                    self.processed_ids.add(tender_id)
                    self._save_processed_ids()
                
                if new_count == 0:
                    print("[✓] Новых тендеров не найдено")
                
                # Проверяем отложенные тендеры
                self.check_pending_tenders()
                
                # Ждём до следующей проверки
                print(f"\n[→] Следующая проверка через {self.config.MONITOR_INTERVAL} секунд...")
                time.sleep(self.config.MONITOR_INTERVAL)
                
            except Exception as e:
                print(f"[✗] Ошибка в цикле мониторинга: {e}")
                time.sleep(60)  # Ждём минуту при ошибке
    
    def check_pending_tenders(self):
        """Проверить отложенные тендеры"""
        now = datetime.now()
        to_process = []
        
        # Собираем тендеры, которые пора обрабатывать
        while not self.pending_queue.empty():
            deadline, tender = self.pending_queue.queue[0]
            if deadline <= now:
                self.pending_queue.get()
                to_process.append(tender)
            else:
                break
        
        # Обрабатываем
        for tender in to_process:
            print(f"\n[!] Обработка отложенного тендера: {tender['title'][:60]}...")
            self.process_tender(tender)
    
    def process_tender(self, tender_data):
        """Обработка тендера: формирование, подпись, подача заявки"""
        from application_manager import ApplicationManager
        
        try:
            # Открываем страницу тендера
            self.bot.open_tender(tender_data["link"])
            
            # Создаём менеджер заявок
            app_manager = ApplicationManager(self.ncanode, self.config)
            
            # Формируем заявку
            application = app_manager.create_application(tender_data)
            
            # Подписываем
            signed_app = app_manager.sign_application(application)
            
            # Сохраняем локально
            app_manager.save_application(signed_app, tender_data.get("number", "unknown"))
            
            # Подаём через Selenium
            success = self.bot.submit_application(signed_app)
            
            if success:
                print(f"[✓] Заявка на тендер {tender_data.get('number', 'N/A')} успешно подана!")
            else:
                print(f"[✗] Не удалось подать заявку на тендер {tender_data.get('number', 'N/A')}")
            
        except Exception as e:
            print(f"[✗] Ошибка обработки тендера: {e}")
