import logging
import random
import requests
from fake_useragent import UserAgent
from config import PROXY_LIST

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
        # Возвращаем более свежий и распространенный User-Agent в случае ошибки
        return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

# Получить случайный рабочий прокси
FAILED_PROXIES = set()
def get_random_proxy():
    global WORKING_PROXIES
    # Сначала проверяем, есть ли WORKING_PROXIES вообще
    if not WORKING_PROXIES:
        # logging.warning("Список WORKING_PROXIES пуст. Запрос прокси невозможен.") # Это уже логгируется в filter_working_proxies
        return None
    available = [p for p in WORKING_PROXIES if p not in FAILED_PROXIES]
    if available:
        return random.choice(available)
    # logging.warning("Нет доступных рабочих прокси (все были отмечены как FAILED_PROXIES или список изначально пуст).")
    return None

def mark_proxy_failed(proxy):
    FAILED_PROXIES.add(proxy)
    logging.warning(f"Прокси {proxy} исключён из пула из-за ошибки.")

def log_info(msg):
    logging.info(msg)

def log_error(msg, exc_info=False):
    logging.error(msg, exc_info=exc_info) 