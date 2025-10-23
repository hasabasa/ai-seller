# Автор: hasabasa

from cryptography.fernet import Fernet
import os
import json

class Config:
    # Основные настройки
    BASE_URL = "https://goszakup.gov.kz"
    CATEGORY = "силовые структуры"
    MONITOR_INTERVAL = 300  # секунды (5 минут)
    MAX_PAGES = 3
    
    # NCANode
    NCANODE_URL = "http://localhost:14579"  # URL NCANode API
    
    # Информация о компании
    COMPANY_INFO = {
        "name": "ТОО \"Ваша Компания\"",
        "bin": "123456789012",
        "address": "г. Астана, ул. Примерная, 1",
        "contact_person": "Иванов Иван Иванович",
        "phone": "+7 701 234 56 78",
        "email": "company@example.kz",
        "delivery_terms": "Доставка за счет поставщика"
    }
    
    # Пути к файлам
    ECP_FILE = "./keys/ecp.p12"  # Путь к файлу ЭЦП (.p12)
    PASSWORD_FILE = "./keys/password.enc"
    KEY_FILE = "./keys/secret.key"
    DOCUMENTS_DIR = "./documents"
    OUTPUT_DIR = "./output"
    LOG_FILE = "./logs/tender_bot.log"

class SecureStorage:
    def __init__(self):
        self.key_file = Config.KEY_FILE
        self.password_file = Config.PASSWORD_FILE
        self._ensure_key()
    
    def _ensure_key(self):
        if not os.path.exists(self.key_file):
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(self.key_file), exist_ok=True)
            with open(self.key_file, 'wb') as f:
                f.write(key)
    
    def save_password(self, password: str):
        with open(self.key_file, 'rb') as f:
            key = f.read()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(password.encode())
        os.makedirs(os.path.dirname(self.password_file), exist_ok=True)
        with open(self.password_file, 'wb') as f:
            f.write(encrypted)
    
    def load_password(self) -> str:
        with open(self.key_file, 'rb') as f:
            key = f.read()
        fernet = Fernet(key)
        with open(self.password_file, 'rb') as f:
            encrypted = f.read()
        return fernet.decrypt(encrypted).decode()

def setup_password():
    storage = SecureStorage()
    password = input("Введите пароль от ЭЦП: ")
    storage.save_password(password)
    print("Пароль сохранён безопасно")

if __name__ == "__main__":
    setup_password()
