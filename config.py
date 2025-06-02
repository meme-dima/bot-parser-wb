import os
from dotenv import load_dotenv

load_dotenv() # Загружаем переменные из .env файла

# Фильтры и параметры
DEFAULT_SEARCH_QUERY = "маска для волос"
DEFAULT_CATEGORY_URL = None
DEFAULT_MAX_PAGES = 2
DEFAULT_MIN_PRICE = 0.0
DEFAULT_MAX_PRICE = 100000.0
DEFAULT_MIN_RATING = 0.0
DEFAULT_MIN_REVIEWS = 0
DEFAULT_BRAND = None
DEFAULT_THREADS = 4
DEFAULT_BATCH_SIZE = 1000
DEFAULT_RANDOM_COUNT = 100

# Пути к файлам
DEFAULT_OUT_JSON = "results.json"
DEFAULT_OUT_CSV = "results.csv"
DEFAULT_ERROR_LOG = "errors.log"
USER_AGENT_FILE = "useragents.txt"
COOKIES_FILE = "cookies.json"

# Telegram
# Загружаем из .env или используем значения по умолчанию
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "") # Оставляем пустую строку как дефолт, если не найдено
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "") # Оставляем пустую строку как дефолт

# Прокси
PROXY_LIST = []
ENABLE_PROXY = True

# Режимы
ENABLE_COOKIES = True
ENABLE_USER_AGENT_LIST = True 