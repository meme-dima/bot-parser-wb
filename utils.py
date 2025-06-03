import logging
import random
import requests
import os
import json
from fake_useragent import UserAgent
from config import PROXY_LIST, COOKIES_FILE

logging.basicConfig(
    filename='wb_parser.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

WORKING_PROXIES = []

# Проверка одного прокси
def check_proxy(proxy, timeout=5):
    try:
        proxies = {"http": proxy, "https": proxy}
        r = requests.get("https://www.wildberries.ru/", proxies=proxies, timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False

def filter_working_proxies():
    global WORKING_PROXIES
    WORKING_PROXIES = [p for p in PROXY_LIST if check_proxy(p)]
    logging.info(f"Рабочих прокси: {len(WORKING_PROXIES)} из {len(PROXY_LIST)}")
    if not WORKING_PROXIES:
        logging.warning("Нет рабочих прокси! Парсер будет работать без прокси.")

# Получить случайный User-Agent
def get_random_user_agent():
    try:
        ua = UserAgent()
        return ua.random
    except Exception:
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Получить случайный рабочий прокси
FAILED_PROXIES = set()
def get_random_proxy():
    global WORKING_PROXIES
    available = [p for p in WORKING_PROXIES if p not in FAILED_PROXIES]
    if available:
        return random.choice(available)
    return None

def mark_proxy_failed(proxy):
    FAILED_PROXIES.add(proxy)
    logging.warning(f"Прокси {proxy} исключён из пула из-за ошибки.")

def log_info(msg):
    logging.info(msg)

def log_error(msg):
    logging.error(msg)

def load_cookies():
    """Загружает cookies из файла COOKIES_FILE (cookies.json)."""
    if not os.path.exists(COOKIES_FILE):
        return []
    with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
        try:
            cookies = json.load(f)
            return cookies
        except Exception as e:
            logging.error(f"Ошибка загрузки cookies: {e}")
            return [] 