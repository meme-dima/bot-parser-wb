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
from telegram_notify import send_telegram_message, send_telegram_file
import logging
import traceback

BATCH_SIZE = 1000  # Количество товаров для промежуточного отчёта
ERROR_LOG = 'errors.log'
PROGRESS_FILE = 'progress.json'

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
        elif submode == '2':
            params['category'] = input("URL категории Wildberries: ").strip()
            params['all_pages'] = True
        else:
            print("Некорректный выбор!")
            sys.exit(1)
    else:
        print("Некорректный выбор!")
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
    return argparse.Namespace(**params)

def process_url(args_tuple):
    url, min_price, max_price, min_rating, min_reviews, brand = args_tuple
    proxy = get_random_proxy()
    try:
        driver = get_driver(proxy, get_random_user_agent())
        data = parse_product_page(driver, url)
        driver.quit()
        if data and filter_product(data, min_price, max_price, min_rating, min_reviews, brand):
            print(f"Подходит: {data['product_name']} ({data['url']})")
            return data
        elif data and data['feedback_discount'] == 0:
            with open(ERROR_LOG, 'a', encoding='utf-8') as f:
                f.write(f"NO_FEEDBACK_DISCOUNT: {url}\n")
    except Exception as e:
        if proxy:
            mark_proxy_failed(proxy)
        log_error(f"Ошибка при обработке {url}: {e}")
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"ERROR: {url} | {e}\n{traceback.format_exc()}\n")
    return None

def send_progress_telegram(total, found, batch_num, total_batches, work_time):
    summary = (
        f"📦 <b>Пакет {batch_num}/{total_batches}</b>\n"
        f"🎯 Обработано ссылок: <b>{total}</b>\n"
        f"💰 Найдено подходящих: <b>{found}</b>\n"
        f"⏰ Время работы: <b>{work_time:.1f} мин</b>\n"
    )
    send_telegram_message(summary)

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
    parser.add_argument('--out-json', type=str, default='results.json', help='Файл для JSON')
    parser.add_argument('--out-csv', type=str, default='results.csv', help='Файл для CSV')
    parser.add_argument('--update-articles', type=str, default=None, help='Файл со списком артикулов для обновления цен')
    parser.add_argument('--random', type=int, default=None, help='Сколько случайных товаров проверить')
    parser.add_argument('--all-pages', action='store_true', help='Собирать все страницы (максимальный сбор)')
    args, unknown = parser.parse_known_args()

    if len(sys.argv) == 1 or all(getattr(args, arg) is None for arg in vars(args)):
        args = interactive_menu()

    filter_working_proxies()  # Проверяем рабочие прокси перед стартом
    start_time = time.time()
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
    log_info(f"Найдено товаров: {len(product_urls)}")
    print(f"Найдено товаров: {len(product_urls)}")
    link_time = time.time() - start_time

    # Многопроцессный парсинг карточек товаров с пакетной отправкой прогресса
    results = []
    args_list = [
        (url, args.min_price, args.max_price, args.min_rating, args.min_reviews, args.brand)
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
        work_time = (time.time() - start_time) / 60
        send_progress_telegram(
            total=min((batch_num+1)*BATCH_SIZE, total),
            found=len(results),
            batch_num=batch_num+1,
            total_batches=total_batches,
            work_time=work_time
        )
        save_progress(batch_num+1, total_batches, min((batch_num+1)*BATCH_SIZE, total), len(results), work_time)
        # Можно сохранять промежуточные результаты в файл, если нужно
    parse_time = time.time() - parse_start
    save_results(results, args.out_json, args.out_csv)
    work_time = (time.time() - start_time) / 60
    # Топ-5 выгодных товаров
    top5 = sorted(results, key=lambda d: d['discount_difference'], reverse=True)[:5]
    top5_str = '\n'.join([
        f"<a href=\"{item['url']}\">{item['product_name']}</a> (разница {item['discount_difference']}₽)"
        for item in top5
    ])
    # Ошибки
    error_count = 0
    no_feedback_count = 0
    if os.path.exists(ERROR_LOG):
        with open(ERROR_LOG, encoding='utf-8') as f:
            lines = f.readlines()
            error_count = sum(1 for l in lines if l.startswith('ERROR:'))
            no_feedback_count = sum(1 for l in lines if l.startswith('NO_FEEDBACK_DISCOUNT:'))
    summary = (
        f"📊 <b>Сводка парсинга WB</b>\n"
        f"🎯 Найдено товаров: <b>{len(product_urls)}</b>\n"
        f"💰 Прибыльных товаров: <b>{len(results)}</b>\n"
        f"❌ Ошибок: <b>{error_count}</b>\n"
        f"🚫 Без скидки за отзыв: <b>{no_feedback_count}</b>\n"
        f"♻️ Дубликатов удалено: <b>{len(product_urls) - len(set([d['article'] for d in results]))}</b>\n"
        f"⏰ Время сбора ссылок: <b>{link_time/60:.1f} мин</b>\n"
        f"⏰ Время парсинга карточек: <b>{parse_time/60:.1f} мин</b>\n"
        f"⏰ Общее время: <b>{work_time:.1f} мин</b>\n"
        f"\n🔥 <b>Топ-5 выгодных:</b>\n{top5_str if top5 else 'Нет'}\n"
        f"\n✅ Парсинг завершён!"
    )
    send_telegram_message(summary)
    # Отправка логов и результатов
    if os.path.exists(ERROR_LOG):
        send_telegram_file(ERROR_LOG, caption="Лог ошибок WB парсера")
    send_telegram_file(args.out_json, caption="Результаты WB парсера (JSON)")
    send_telegram_file(args.out_csv, caption="Результаты WB парсера (CSV)")
    print(f"Сохранено: {len(results)} товаров. JSON: {args.out_json}, CSV: {args.out_csv}")
    print("Уведомление и файлы отправлены в Telegram!")

if __name__ == "__main__":
    main() 