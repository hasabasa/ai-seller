from playwright.sync_api import sync_playwright
import time
import random

def human_pause(a=1.3, b=2.7):
    time.sleep(random.uniform(a, b))

def playwright_login(password):
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    page.goto("https://goszakup.gov.kz/ru/user")
    human_pause()

    # Вход через ЭЦП
    page.locator("button:has-text('ЭЦП'), a:has-text('ЭЦП')").click()
    human_pause()

    # Второй этап: галочка согласия и повторный пароль
    page.wait_for_selector("#agreed_check", timeout=12000)
    checkbox = page.locator("#agreed_check")
    if not checkbox.is_checked():
        checkbox.click()
        human_pause(0.8,1.7)

    pwd_input = page.locator("input.form-control[name='password']")
    pwd_input.fill(password)
    human_pause()

    page.locator("button.btn.btn-success[type='submit']").click()
    human_pause(1.5, 2.5)

    # Проверить успешный кабинет
    page.wait_for_selector("a[href*='cabinet']", timeout=17000)
    print("[✓] Авторизация через Playwright выполнена")

    # Возвращаем page, context и browser — чтобы работать дальше!
    return page, context, browser
