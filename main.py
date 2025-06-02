import argparse
import json
import pandas as pd
import os
import random
import sys
import time
from multiprocessing import Pool, cpu_count
from parser import get_driver, get_product_links, get_all_product_links, parse_product_page
from filters import filter_product
from utils import get_random_user_agent, get_random_proxy, log_info, log_error, filter_working_proxies, mark_proxy_failed
from config import *
# import telegram_notify # Удаляем, так как bot.py будет обрабатывать уведомления
import logging
import traceback

BATCH_SIZE = 1000  # Количество товаров для промежуточного отчёта
# ERROR_LOG = 'errors.log' # Будет использоваться args.error_log
PROGRESS_FILE = 'progress.json'

# Настройка логирования для main.py (если еще не настроено глобально)
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("main_parser.log"), # Лог самого main.py
            logging.StreamHandler()
        ]
    )

def save_results(results, out_json, out_csv):
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    df = pd.DataFrame(results)
    df.to_csv(out_csv, index=False, encoding='utf-8-sig')

def generate_random_articles(n, min_id=1000000, max_id=999999999):
    return [random.randint(min_id, max_id) for _ in range(n)]

def interactive_menu():
    print("Выберите режим:")
    print("1. Поиск по ключевому слову (ограниченное число страниц)")
    print("2. Поиск по категории (ограниченное число страниц)")
    print("3. Обновление по списку артикулов")
    print("4. Случайные товары")
    print("5. Максимальный сбор (все товары из поиска или категории)")
    mode = input("Ваш выбор (1-5): ").strip()
    params = {}
    if mode == '1':
        params['search'] = input("Ключевое слово для поиска: ").strip()
        params['pages'] = int(input("Сколько страниц парсить (по 100 товаров на страницу): ").strip() or DEFAULT_MAX_PAGES)
    elif mode == '2':
        params['category'] = input("URL категории Wildberries: ").strip()
        params['pages'] = int(input("Сколько страниц парсить: ").strip() or DEFAULT_MAX_PAGES)
    elif mode == '3':
        params['update_articles'] = input("Путь к файлу со списком артикулов: ").strip()
    elif mode == '4':
        params['random'] = int(input("Сколько случайных товаров проверить: ").strip())
    elif mode == '5':
        submode = input("1 — Поиск по ключу, 2 — По категории: ").strip()
        if submode == '1':
            params['search'] = input("Ключевое слово для поиска: ").strip()
            params['all_pages'] = True
            logger.info(f"Интерактивный режим: максимальный сбор по ключу '{params['search']}'")
        elif submode == '2':
            params['category'] = input("URL категории Wildberries: ").strip()
            params['all_pages'] = True
            logger.info(f"Интерактивный режим: максимальный сбор по категории '{params['category']}'")
        else:
            print("Некорректный выбор!")
            logger.error("Интерактивный режим: некорректный выбор подрежима для максимального сбора.")
            sys.exit(1)
    else:
        print("Некорректный выбор!")
        logger.error(f"Интерактивный режим: некорректный выбор режима '{mode}'.")
        sys.exit(1)
    # Общие фильтры
    params['min_price'] = float(input(f"Мин. цена (по умолчанию {DEFAULT_MIN_PRICE}): ").strip() or DEFAULT_MIN_PRICE)
    params['max_price'] = float(input(f"Макс. цена (по умолчанию {DEFAULT_MAX_PRICE}): ").strip() or DEFAULT_MAX_PRICE)
    params['min_rating'] = float(input(f"Мин. рейтинг (по умолчанию {DEFAULT_MIN_RATING}): ").strip() or DEFAULT_MIN_RATING)
    params['min_reviews'] = int(input(f"Мин. кол-во отзывов (по умолчанию {DEFAULT_MIN_REVIEWS}): ").strip() or DEFAULT_MIN_REVIEWS)
    params['brand'] = input("Фильтр по бренду (опционально): ").strip() or None
    params['threads'] = int(input(f"Потоков для парсинга (по умолчанию {cpu_count()}): ").strip() or cpu_count())
    params['out_json'] = input("Файл для JSON (по умолчанию results.json): ").strip() or 'results.json'
    params['out_csv'] = input("Файл для CSV (по умолчанию results.csv): ").strip() or 'results.csv'
    params['error_log'] = input(f"Файл для лога ошибок (по умолчанию {DEFAULT_ERROR_LOG}): ").strip() or DEFAULT_ERROR_LOG
    logger.info(f"Интерактивный режим: выбраны параметры {params}")
    return argparse.Namespace(**params)

def process_url(args_tuple):
    url, min_price, max_price, min_rating, min_reviews, brand, error_log_file = args_tuple
    proxy = get_random_proxy()
    try:
        driver = get_driver(proxy, get_random_user_agent())
        data = parse_product_page(driver, url)
        driver.quit()
        if data and filter_product(data, min_price, max_price, min_rating, min_reviews, brand):
            # print(f"Подходит: {data['product_name']} ({data['url']})") # Заменено на логгер
            logger.info(f"Подходит: {data['product_name']} ({data['url']})")
            return data
        elif data and data['feedback_discount'] == 0: # Это условие специфично, возможно, стоит пересмотреть или сделать настраиваемым
            with open(error_log_file, 'a', encoding='utf-8') as f:
                f.write(f"NO_FEEDBACK_DISCOUNT: {url}\\n")
            logger.info(f"Товар {url} отфильтрован (нет скидки за отзыв или цена >= скидке).") # Уточнено условие в filters.py
    except Exception as e:
        if proxy:
            mark_proxy_failed(proxy) # Эта функция логгирует сама
        # log_error(f"Ошибка при обработке {url}: {e}") # log_error из utils пишет в wb_parser.log, здесь лучше использовать логгер main.py или передавать его
        logger.error(f"Ошибка при обработке {url}: {e}", exc_info=True)
        with open(error_log_file, 'a', encoding='utf-8') as f:
            f.write(f"ERROR: {url} | {e}\\n{traceback.format_exc()}\\n")
    return None

def save_progress(batch_num, total_batches, total, found, work_time):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'batch_num': batch_num,
            'total_batches': total_batches,
            'total': total,
            'found': found,
            'work_time': work_time
        }, f, ensure_ascii=False)

def main():
    parser = argparse.ArgumentParser(description="Wildberries парсер с фильтрами и Telegram-уведомлением.")
    parser.add_argument('--search', type=str, default=None, help='Поисковый запрос')
    parser.add_argument('--category', type=str, default=None, help='URL категории Wildberries')
    parser.add_argument('--pages', type=int, default=DEFAULT_MAX_PAGES, help='Сколько страниц парсить')
    parser.add_argument('--min-price', type=float, default=DEFAULT_MIN_PRICE, help='Мин. цена')
    parser.add_argument('--max-price', type=float, default=DEFAULT_MAX_PRICE, help='Макс. цена')
    parser.add_argument('--min-rating', type=float, default=DEFAULT_MIN_RATING, help='Мин. рейтинг')
    parser.add_argument('--min-reviews', type=int, default=DEFAULT_MIN_REVIEWS, help='Мин. кол-во отзывов')
    parser.add_argument('--brand', type=str, default=None, help='Фильтр по бренду')
    parser.add_argument('--threads', type=int, default=cpu_count(), help='Потоков/процессов для парсинга')
    parser.add_argument('--out-json', type=str, default=DEFAULT_OUT_JSON, help='Файл для JSON') # Используем DEFAULT_OUT_JSON
    parser.add_argument('--out-csv', type=str, default=DEFAULT_OUT_CSV, help='Файл для CSV') # Используем DEFAULT_OUT_CSV
    parser.add_argument('--error-log', type=str, default=DEFAULT_ERROR_LOG, help='Файл для лога ошибок') # Новый аргумент
    parser.add_argument('--update-articles', type=str, default=None, help='Файл со списком артикулов для обновления цен')
    parser.add_argument('--random', type=int, default=None, help='Сколько случайных товаров проверить')
    parser.add_argument('--all-pages', action='store_true', help='Собирать все страницы (максимальный сбор)')
    args, unknown = parser.parse_known_args()

    if unknown:
        logger.warning(f"Обнаружены неизвестные аргументы: {unknown}")

    # Настройка обработчика файла для лога ошибок парсинга, если он отличается от основного лога main_parser.log
    # Это больше для ошибок отдельных URL, а не общих ошибок main.py
    # Основные ошибки main.py уже пишутся в main_parser.log
    # Можно также настроить отдельный логгер для ошибок URL, если это требуется

    if not any(vars(args).values()): # Проверка, что хоть какой-то аргумент был передан (кроме action='store_true')
        # Эвристика: если только --all-pages или вообще ничего, то интерактивное меню
        # Более точная проверка: если все значимые аргументы None или False (для store_true)
        meaningful_args_provided = any(
            getattr(args, arg) for arg in ['search', 'category', 'update_articles', 'random']
        )
        if not meaningful_args_provided and not (len(sys.argv) > 1 and sys.argv[1] not in ['--all-pages']): # Проверяем, что не просто флаг
             logger.info("Не предоставлены аргументы командной строки, запускаю интерактивное меню.")
             args = interactive_menu()
        elif not meaningful_args_provided and args.all_pages and not (getattr(args, 'search', None) or getattr(args, 'category', None)):
            logger.warning("Выбран --all-pages, но не указан --search или --category. Запускаю интерактивное меню.")
            args = interactive_menu() # Если all_pages, но нет search/category
        else:
            logger.info(f"Запуск с аргументами командной строки: {args}")

    filter_working_proxies()  # Проверяем рабочие прокси перед стартом
    start_time = time.time()
    logger.info(f"Парсер запущен. Аргументы: {args}")
    # Сбор ссылок
    link_time = None
    if getattr(args, 'random', None):
        articles = generate_random_articles(args.random)
        product_urls = [f"https://www.wildberries.ru/catalog/{art}/detail.aspx" for art in articles]
    elif getattr(args, 'update_articles', None):
        with open(args.update_articles, encoding='utf-8') as f:
            articles = [line.strip() for line in f if line.strip()]
        product_urls = [f"https://www.wildberries.ru/catalog/{art}/detail.aspx" for art in articles]
    elif getattr(args, 'all_pages', False):
        driver = get_driver(get_random_proxy(), get_random_user_agent())
        product_urls = get_all_product_links(driver, getattr(args, 'search', None), getattr(args, 'category', None))
        driver.quit()
    elif getattr(args, 'category', None):
        driver = get_driver(get_random_proxy(), get_random_user_agent())
        product_urls = get_product_links(driver, None, args.category, args.pages)
        driver.quit()
    else:
        driver = get_driver(get_random_proxy(), get_random_user_agent())
        product_urls = get_product_links(driver, args.search or DEFAULT_SEARCH_QUERY, None, args.pages)
        driver.quit()
    product_urls = list(set(product_urls))
    # log_info(f"Найдено товаров: {len(product_urls)}") # Заменено на logger
    logger.info(f"Найдено уникальных ссылок на товары: {len(product_urls)}")
    # print(f"Найдено товаров: {len(product_urls)}") # Заменено на logger

    link_time = time.time() - start_time
    logger.info(f"Время сбора ссылок: {link_time:.2f} сек")

    # Многопроцессный парсинг карточек товаров с пакетной отправкой прогресса
    results = []
    args_list = [
        (url, args.min_price, args.max_price, args.min_rating, args.min_reviews, args.brand, args.error_log) # Передаем error_log
        for url in product_urls
    ]
    total = len(args_list)
    total_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    parse_start = time.time()
    for batch_num in range(total_batches):
        batch_args = args_list[batch_num*BATCH_SIZE:(batch_num+1)*BATCH_SIZE]
        batch_results = []
        with Pool(processes=args.threads) as pool:
            for data in pool.imap_unordered(process_url, batch_args):
                if data:
                    results.append(data)
                    batch_results.append(data)
        # Промежуточный отчёт
        work_time_batch = (time.time() - start_time) / 60
        processed_count = min((batch_num + 1) * BATCH_SIZE, total)
        logger.info(f"Пакет {batch_num+1}/{total_batches} завершен. Обработано: {processed_count}/{total}. Найдено: {len(results)}. Время: {work_time_batch:.1f} мин.")
        # Удаляем вызов send_progress_telegram
        save_progress(batch_num + 1, total_batches, processed_count, len(results), work_time_batch)
        # Можно сохранять промежуточные результаты в файл, если нужно
        if batch_results: # Сохраняем промежуточные результаты батча, если они есть
             # Это может быть полезно для очень долгих задач, но увеличит IO.
             # Пока оставим только финальное сохранение.
             pass

    parse_time = time.time() - parse_start
    logger.info(f"Время парсинга карточек: {parse_time / 60:.1f} мин")
    save_results(results, args.out_json, args.out_csv)
    logger.info(f"Результаты сохранены: {len(results)} товаров. JSON: {args.out_json}, CSV: {args.out_csv}")
    work_time = (time.time() - start_time) / 60
    # Топ-5 выгодных товаров
    top5 = sorted(results, key=lambda d: d.get('discount_difference', 0), reverse=True)[:5]
    if top5:
        logger.info("Топ-5 выгодных (по разнице скидки):")
        for item in top5:
            logger.info(f"- {item.get('product_name', 'N/A')} ({item.get('url', 'N/A')}), разница {item.get('discount_difference', 0)}₽")
    else:
        logger.info("Топ-5 выгодных: Нет")

    # Формируем сводку для лога
    summary_log = (
        f"Сводка парсинга WB:\\n"
        f"Найдено ссылок на товары: {len(product_urls)}\\n"
        f"Отфильтровано (подходящих) товаров: {len(results)}\\n"
        f"Ошибок при обработке URL: {sum(1 for l in open(args.error_log, encoding='utf-8') if l.startswith('ERROR:'))}\\n"
        f"Товаров без скидки за отзыв (или цена выше): {sum(1 for l in open(args.error_log, encoding='utf-8') if l.startswith('NO_FEEDBACK_DISCOUNT:'))}\\n"
        f"Время сбора ссылок: {link_time / 60:.1f} мин\\n"
        f"Время парсинга карточек: {parse_time / 60:.1f} мин\\n"
        f"Общее время: {work_time:.1f} мин\\n"
    )
    if results:
        unique_articles_found = len(set(d['article'] for d in results if 'article' in d))
        summary_log += f"Уникальных артикулов среди найденных: {unique_articles_found}\\n"
        if len(product_urls) > 0 and unique_articles_found > 0: # Предотвращение деления на ноль
             # Эта метрика может быть не очень полезна, т.к. product_urls это ссылки, а не артикулы
             pass

    summary_log += "Парсинг завершён!"
    logger.info(summary_log.replace('\\n', '\\n')) # Логируем итоговую сводку

    # Удаляем отправку уведомлений и файлов в Telegram из main.py
    # send_telegram_message(summary)
    # if os.path.exists(args.error_log):
    #     send_telegram_file(args.error_log, caption="Лог ошибок WB парсера")
    # send_telegram_file(args.out_json, caption="Результаты WB парсера (JSON)")
    # send_telegram_file(args.out_csv, caption="Результаты WB парсера (CSV)")

    print(f"Сохранено: {len(results)} товаров. JSON: {args.out_json}, CSV: {args.out_csv}, Лог ошибок: {args.error_log}")
    # print("Уведомление и файлы отправлены в Telegram!") # Удалено
    logger.info("Скрипт main.py завершил работу.")

if __name__ == "__main__":
    # Настройка логирования здесь, если main.py запускается напрямую
    # Если он импортируется, логгер уже должен быть настроен или настроится при первом вызове getLogger
    if not logging.getLogger(__name__).handlers: # Проверка, чтобы не дублировать хендлеры при прямом запуске
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("main_parser_direct_run.log"), # Отдельный лог для прямого запуска
                logging.StreamHandler()
            ]
        )
    logger.info("main.py запущен напрямую.")
    main() 