#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Автор: hasabasa

import sys
from config import Config
from tender_monitor import TenderMonitor
from ncanode_client import NCANodeClient
from security_manager import SecurityManager
from playwright_automation import playwright_login

def main():
    print("="*80)
    print("СИСТЕМА АВТОМАТИЗАЦИИ УЧАСТИЯ В ТЕНДЕРАХ (на Playwright)")
    print("Категория: Силовые структуры РК")
    print("Автор: hasabasa")
    print("="*80)
    
    # Проверка настройки безопасного хранилища
    security = SecurityManager()
    if not security.verify_setup():
        print("\n[✗] Безопасное хранилище не настроено!")
        print("Запустите: python security_manager.py")
        sys.exit(1)
    
    config = Config()
    
    # Инициализация NCANode
    print("\n[→] Инициализация NCANode...")
    ncanode = NCANodeClient(config.NCANODE_URL)
    try:
        key_info = ncanode.get_key_info()
        print(f"[✓] NCANode доступен, ЭЦП валидна")
    except Exception as e:
        print(f"[✗] Ошибка проверки NCANode/ЭЦП: {e}")
        print("Убедитесь, что NCANode запущен на", config.NCANODE_URL)
        sys.exit(1)

    # Авторизация через Playwright
    page, context, browser = None, None, None
    try:
        print("\n[→] Авторизация на портале через Playwright...")
        password = security.decrypt_ecp_password()
        page, context, browser = playwright_login(password)
        
        # Передаем управление монитору
        # Обратите внимание, что TenderMonitor нужно будет адаптировать для работы с `page`
        # Вместо `bot.driver.get()` -> `page.goto()`
        # Вместо `bot.driver.find_element()` -> `page.locator()` и т.д.
        
        # Пример перехода и поиска тендеров:
        print("\n[→] Переход к поиску тендеров...")
        page.goto("https://goszakup.gov.kz/ru/search/announce?filter[category]=силовые структуры")

        print("[→] Поиск карточек тендеров...")
        cards = page.locator("div.tender-item, div.announce-item, tr.tender-row")
        count = cards.count()
        print(f"Найдено {count} тендеров на странице.")
        for i in range(min(count, 5)): # Выводим первые 5 для примера
            title = cards.nth(i).locator("h3, a.title").inner_text()
            print(f"  - Тендер: {title.strip()}")

        # Здесь должен быть запуск цикла мониторинга, адаптированного под Playwright
        # monitor = TenderMonitor(page, ncanode, config)
        # monitor.monitor_loop()

    except KeyboardInterrupt:
        print("\n\n[!] Остановка по запросу пользователя")
    except Exception as e:
        print(f"\n[✗] Ошибка в процессе работы: {e}")
    finally:
        # Корректное закрытие ресурсов Playwright
        if context:
            context.close()
        if browser:
            browser.close()
        print("\n[→] Браузер закрыт. Завершение работы.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[✗] Критическая ошибка: {e}")
        sys.exit(1)
