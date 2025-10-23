# Автор: hasabasa

import os
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from cryptography.hazmat.backends import default_backend
import getpass
import json

class SecurityManager:
    """
    Управление безопасным хранением ЭЦП и пароля
    """
    
    def __init__(self, keys_dir="./keys"):
        self.keys_dir = keys_dir
        self.master_key_file = os.path.join(keys_dir, "master.key")
        self.encrypted_password_file = os.path.join(keys_dir, "ecp_password.enc")
        self.encrypted_ecp_file = os.path.join(keys_dir, "ecp.p12.enc")
        self.salt_file = os.path.join(keys_dir, "salt.dat")
        
        os.makedirs(keys_dir, exist_ok=True)
        self._ensure_master_key()
    
    def _ensure_master_key(self):
        """Создать или загрузить мастер-ключ"""
        if not os.path.exists(self.master_key_file):
            # Генерируем новый мастер-ключ
            key = Fernet.generate_key()
            with open(self.master_key_file, 'wb') as f:
                f.write(key)
            # Устанавливаем права только для владельца (Unix)
            if os.name != 'nt':
                os.chmod(self.master_key_file, 0o600)
            print("[✓] Создан новый мастер-ключ")
    
    def _get_master_key(self):
        """Получить мастер-ключ"""
        with open(self.master_key_file, 'rb') as f:
            return f.read()
    
    def encrypt_ecp_password(self, password: str):
        """
        Зашифровать пароль от ЭЦП
        Использует мастер-ключ
        """
        key = self._get_master_key()
        fernet = Fernet(key)
        
        encrypted = fernet.encrypt(password.encode())
        
        with open(self.encrypted_password_file, 'wb') as f:
            f.write(encrypted)
        
        if os.name != 'nt':
            os.chmod(self.encrypted_password_file, 0o600)
        
        print("[✓] Пароль от ЭЦП зашифрован и сохранён")
    
    def decrypt_ecp_password(self) -> str:
        """Расшифровать пароль от ЭЦП"""
        if not os.path.exists(self.encrypted_password_file):
            raise FileNotFoundError("Зашифрованный пароль не найден. Запустите: python security_manager.py")
        
        key = self._get_master_key()
        fernet = Fernet(key)
        
        with open(self.encrypted_password_file, 'rb') as f:
            encrypted = f.read()
        
        return fernet.decrypt(encrypted).decode()
    
    def encrypt_ecp_file(self, source_p12_path: str):
        """
        Зашифровать файл ЭЦП (.p12)
        После шифрования оригинальный файл можно удалить
        """
        if not os.path.exists(source_p12_path):
            raise FileNotFoundError(f"Файл ЭЦП не найден: {source_p12_path}")
        
        # Читаем оригинальный файл
        with open(source_p12_path, 'rb') as f:
            ecp_data = f.read()
        
        # Шифруем мастер-ключом
        key = self._get_master_key()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(ecp_data)
        
        # Сохраняем зашифрованный
        with open(self.encrypted_ecp_file, 'wb') as f:
            f.write(encrypted)
        
        if os.name != 'nt':
            os.chmod(self.encrypted_ecp_file, 0o600)
        
        print("[✓] Файл ЭЦП зашифрован и сохранён")
        print(f"[!] Можно безопасно удалить оригинал: {source_p12_path}")
    
    def decrypt_ecp_file(self) -> bytes:
        """
        Расшифровать файл ЭЦП
        Возвращает содержимое в памяти (не сохраняет на диск)
        """
        if not os.path.exists(self.encrypted_ecp_file):
            raise FileNotFoundError("Зашифрованный файл ЭЦП не найден")
        
        key = self._get_master_key()
        fernet = Fernet(key)
        
        with open(self.encrypted_ecp_file, 'rb') as f:
            encrypted = f.read()
        
        return fernet.decrypt(encrypted)
    
    def get_ecp_base64(self) -> str:
        """
        Получить ЭЦП в формате Base64 для передачи в NCANode
        """
        ecp_bytes = self.decrypt_ecp_file()
        return base64.b64encode(ecp_bytes).decode()
    
    def setup_interactive(self):
        """
        Интерактивная настройка - первый запуск
        """
        print("="*60)
        print("НАСТРОЙКА БЕЗОПАСНОГО ХРАНИЛИЩА ЭЦП")
        print("="*60)
        
        # 1. Путь к файлу ЭЦП
        ecp_path = input("\nВведите путь к файлу ЭЦП (.p12): ").strip()
        if not os.path.exists(ecp_path):
            print(f"[✗] Файл не найден: {ecp_path}")
            return False
        
        # 2. Пароль от ЭЦП
        password = getpass.getpass("Введите пароль от ЭЦП: ")
        password_confirm = getpass.getpass("Подтвердите пароль: ")
        
        if password != password_confirm:
            print("[✗] Пароли не совпадают")
            return False
        
        # 3. Шифруем
        print("\n[→] Шифрование данных...")
        self.encrypt_ecp_file(ecp_path)
        self.encrypt_ecp_password(password)
        
        print("\n" + "="*60)
        print("[✓] НАСТРОЙКА ЗАВЕРШЕНА")
        print("="*60)
        print("\nВаши данные зашифрованы и защищены.")
        print(f"Мастер-ключ: {self.master_key_file}")
        print(f"ЭЦП (зашифрована): {self.encrypted_ecp_file}")
        print(f"Пароль (зашифрован): {self.encrypted_password_file}")
        print("\n⚠️  ВАЖНО: Храните мастер-ключ в безопасности!")
        print("⚠️  Без него невозможно расшифровать ваши данные!")
        
        return True
    
    def verify_setup(self) -> bool:
        """Проверить, что всё настроено"""
        required_files = [
            self.master_key_file,
            self.encrypted_password_file,
            self.encrypted_ecp_file
        ]
        
        for file_path in required_files:
            if not os.path.exists(file_path):
                return False
        
        return True
    
    def export_config(self, output_file="ecp_config.json"):
        """
        Экспорт конфигурации (БЕЗ секретных данных)
        Для документирования настроек
        """
        config = {
            "keys_directory": self.keys_dir,
            "setup_complete": self.verify_setup(),
            "master_key_exists": os.path.exists(self.master_key_file),
            "ecp_encrypted_exists": os.path.exists(self.encrypted_ecp_file),
            "password_encrypted_exists": os.path.exists(self.encrypted_password_file)
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"[✓] Конфигурация сохранена: {output_file}")


def main():
    """
    Скрипт первичной настройки
    Запустить один раз для настройки безопасного хранилища
    """
    sm = SecurityManager()
    
    if sm.verify_setup():
        print("[!] Хранилище уже настроено")
        choice = input("Перенастроить? (y/n): ")
        if choice.lower() != 'y':
            return
    
    if sm.setup_interactive():
        print("\n[✓] Теперь можно запускать основной скрипт")
        print("Запустите: python main.py")
    else:
        print("\n[✗] Настройка не завершена")


if __name__ == "__main__":
    main()
