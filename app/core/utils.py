import logging
import random
import os # Добавлен импорт os
# fake_useragent может вызывать проблемы при сборке или на некоторых системах,
# поэтому лучше иметь простой список User-Agent как фолбек.
# from fake_useragent import UserAgent 
from .config import PROXY_LIST # ИЗМЕНЕН ИМПОРТ

# Пример User-Agent
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

# --- Создание папки для логов и debug файла --- #
LOG_DIR = 'app/data'
GENERAL_LOG_FILE_PATH = os.path.join(LOG_DIR, 'wildberries_parser.log')
PROCESSED_ITEMS_LOG_FILE_PATH = os.path.join(LOG_DIR, 'processed_items.log') # Новый файл лога

# Получаем корневой логгер и логгер для обработанных элементов
# Настраивать их будем в setup_logging
general_logger = logging.getLogger("general")
processed_items_logger = logging.getLogger("processed_items")

def setup_logging():
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # Настройка основного логгера
    general_logger.setLevel(logging.INFO)
    general_formatter = logging.Formatter('%(asctime)s %(levelname)s:%(message)s')
    general_handler = logging.FileHandler(GENERAL_LOG_FILE_PATH, encoding='utf-8') # Добавим encoding
    general_handler.setFormatter(general_formatter)
    general_logger.addHandler(general_handler)
    # Чтобы избежать двойного логирования, если basicConfig был вызван где-то еще
    general_logger.propagate = False 

    # Настройка логгера для обработанных товаров
    processed_items_logger.setLevel(logging.INFO)
    processed_formatter = logging.Formatter('%(asctime)s: %(message)s')
    processed_handler = logging.FileHandler(PROCESSED_ITEMS_LOG_FILE_PATH, encoding='utf-8') # Добавим encoding
    processed_handler.setFormatter(processed_formatter)
    processed_items_logger.addHandler(processed_handler)
    processed_items_logger.propagate = False

    # Убираем старый logging.basicConfig, так как мы настроили логгеры вручную
    # logging.basicConfig(
    #     filename=GENERAL_LOG_FILE_PATH, 
    #     level=logging.INFO,
    #     format='%(asctime)s %(levelname)s:%(message)s'
    # )

def get_random_user_agent():
    # try:
    #     ua = UserAgent()
    #     return ua.random
    # except Exception:
    #     # Фолбек
    #     return random.choice(USER_AGENTS)
    return random.choice(USER_AGENTS)

def get_random_proxy():
    if PROXY_LIST:
        return random.choice(PROXY_LIST)
    return None

def log_info(msg):
    general_logger.info(msg)

def log_error(msg):
    general_logger.error(msg)

def log_warning(msg):
    general_logger.warning(msg)

def log_processed_item(msg): # Новая функция логирования
    processed_items_logger.info(msg) 