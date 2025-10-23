# Автор: hasabasa

import requests
import base64
from security_manager import SecurityManager

class NCANodeClient:
    def __init__(self, ncanode_url="http://localhost:14579"):
        self.base_url = ncanode_url
        self.key_data = None
        self.password = None
        self.security = SecurityManager()
    
    def load_credentials(self):
        """
        Загрузить ЭЦП и пароль из безопасного хранилища
        """
        if not self.security.verify_setup():
            raise Exception("Хранилище не настроено. Запустите: python security_manager.py")
        
        # Загружаем ЭЦП в Base64
        self.key_data = self.security.get_ecp_base64()
        
        # Загружаем пароль
        self.password = self.security.decrypt_ecp_password()
        
        print("[✓] Учётные данные ЭЦП загружены из безопасного хранилища")
    
    def sign_xml(self, xml_data):
        """Подписать XML через NCANode"""
        if not self.key_data or not self.password:
            raise Exception("Учётные данные не загружены. Вызовите load_credentials()")
        
        payload = {
            "xml": xml_data,
            "signers": [{
                "key": self.key_data,
                "password": self.password
            }]
        }
        
        response = requests.post(
            f"{self.base_url}/xmldsig/sign",
            json=payload,
            timeout=30
        )
        
        result = response.json()
        if result.get('status') == 200:
            return result.get('xml')
        else:
            raise Exception(f"Ошибка подписи XML: {result.get('message')}")
    
    def sign_cms(self, data):
        """Подписать данные в CMS формате"""
        if not self.key_data or not self.password:
            raise Exception("Учётные данные не загружены")
        
        data_b64 = base64.b64encode(data.encode()).decode()
        
        payload = {
            "data": data_b64,
            "signers": [{
                "key": self.key_data,
                "password": self.password
            }]
        }
        
        response = requests.post(
            f"{self.base_url}/cms/sign",
            json=payload,
            timeout=30
        )
        
        result = response.json()
        if result.get('status') == 200:
            return result.get('cms')
        else:
            raise Exception(f"Ошибка подписи CMS: {result.get('message')}")
    
    def verify_cms(self, cms_data):
        """Проверить CMS подпись"""
        payload = {"cms": cms_data}
        
        response = requests.post(
            f"{self.base_url}/cms/verify",
            json=payload,
            timeout=30
        )
        
        return response.json()
    
    def get_key_info(self):
        """Получить информацию о ключе"""
        if not self.key_data or not self.password:
            raise Exception("Учётные данные не загружены")
        
        payload = {
            "key": self.key_data,
            "password": self.password
        }
        
        response = requests.post(
            f"{self.base_url}/key/info",
            json=payload,
            timeout=30
        )
        
        return response.json()
