# Автор: hasabasa

import json
import os
from datetime import datetime

class ApplicationManager:
    def __init__(self, ncanode_client, config):
        self.ncanode = ncanode_client
        self.config = config
    
    def create_application(self, tender_data):
        """Создать заявку на основе данных тендера"""
        application = {
            "tender_number": tender_data.get("number"),
            "tender_title": tender_data.get("title"),
            "tender_link": tender_data.get("link"),
            "applicant": self.config.COMPANY_INFO,
            "proposed_price": tender_data.get("amount"),
            "created_at": datetime.now().isoformat()
        }
        return application
    
    def sign_application(self, application):
        """Подписать заявку через ЭЦП"""
        try:
            # Формируем данные для подписи
            data_to_sign = json.dumps(application, ensure_ascii=False, sort_keys=True)
            
            # Подписываем через NCANode (CMS)
            signature = self.ncanode.sign_cms(data_to_sign)
            
            # Добавляем подпись к заявке
            application["signature"] = signature
            application["signed_at"] = datetime.now().isoformat()
            
            print("[✓] Заявка подписана через ЭЦП")
            return application
            
        except Exception as e:
            print(f"[✗] Ошибка подписи заявки: {e}")
            raise
    
    def save_application(self, application, tender_number):
        """Сохранить заявку локально"""
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        filename = f"application_{tender_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(self.config.OUTPUT_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(application, f, ensure_ascii=False, indent=2)
        
        print(f"[✓] Заявка сохранена: {filename}")
