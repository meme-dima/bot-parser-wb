from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, URLInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.core.parser import get_driver, parse_product_page, get_product_links
from app.core.utils import log_info, log_error, log_warning, log_processed_item
import asyncio
import random

# --- Текстовые константы ---
MSG_GREETING = (
    "Привет! Я бот для парсинга Wildberries. Нажми кнопку или отправь ссылку на товар.\n\n"
    "Или используй команду /find_deals для поиска выгодных предложений!"
)
MSG_ASK_LINK = "Пришли ссылку на товар Wildberries:"
MSG_PARSING_STARTED = "Начинаю парсинг для: {url}\nПожалуйста, подожди..."
MSG_ASK_SEARCH_QUERY = "Введите поисковый запрос для поиска выгодных товаров (например, 'беспроводные наушники'):"
MSG_EMPTY_SEARCH_QUERY = "Поисковый запрос не может быть пустым. Пожалуйста, введите запрос:"
MSG_ASK_NUM_PAGES = "Сколько страниц поисковой выдачи проверить? (Введите число, например, 3)"
MSG_INVALID_NUM_PAGES_POSITIVE = "Количество страниц должно быть положительным числом. Попробуйте еще раз:"
MSG_INVALID_NUM_PAGES_FORMAT = "Пожалуйста, введите корректное число страниц (например, 3):"
MSG_SEARCH_STARTED = "Начинаю поиск по запросу: '{search_query}' на {num_pages_to_check} страницах... Это может занять некоторое время."
MSG_SEARCH_STARTED_PARALLEL = "Начинаю поиск по запросу: '{search_query}' на {num_pages_to_check} стр. Запускаю {worker_count} параллельных обработчиков для {link_count} ссылок..."
MSG_NO_LINKS_FOUND = "По запросу '{search_query}' ничего не найдено на указанном количестве страниц."
MSG_LINKS_FOUND_START_PROCESSING = "Найдено {count} товаров. Начинаю проверку на выгодные предложения..."
MSG_ITEMS_CHECKED_PROGRESS = "Проверено {checked} из {total} товаров..."
MSG_SEARCH_COMPLETED = "Поиск завершен. Проверено товаров: {processed} из {total_links}. Найдено выгодных предложений: {deals_count}."
MSG_CAPTCHA_DETECTED = "Не удалось получить данные: обнаружена капча на странице {url}. Попробуйте позже или другую ссылку."
MSG_PARSE_ERROR_DEBUG_HTML = "Не удалось полностью разобрать страницу для: {url}. Проверьте debug_wb.html. {message}"
MSG_DATA_NOT_FOUND = "Не удалось получить данные для: {url}. Возможно, изменилась структура страницы, товар недоступен или другая ошибка."
MSG_CRITICAL_ERROR_PROCESSING_LINK = "Произошла критическая ошибка при обработке ссылки: {url}. Попробуйте позже."
MSG_ERROR_GETTING_LINKS = "Не удалось получить список товаров для поиска. Попробуйте позже."
MSG_DRIVER_INIT_FAILED_FOR_ITEMS = "Не удалось инициализировать драйвер для проверки товаров. Поиск прерван."
MSG_ERROR_IN_ITEM_PROCESSING_LOOP = "Во время проверки товаров произошла ошибка. Поиск может быть неполным."
MSG_PRODUCT_UNAVAILABLE = "Товар по ссылке {url} недоступен (возможно, распродан или страница не существует). Сообщение: {message}"
MSG_ESSENTIAL_DATA_MISSING = "Не удалось извлечь ключевые данные (название/цена) для товара: {url}. {message}"

DEAL_ALERT_PREFIX = "🔥 <b>ВЫГОДНОЕ ПРЕДЛОЖЕНИЕ!</b> Цена ниже скидки за отзыв!\n"

# --- Константы для логики ---
WB_URL_REGEX = r"https://www\.wildberries\.ru/catalog/\d+/detail\.aspx"
MAX_CONCURRENT_PARSERS = 4 # Количество одновременных парсеров

router = Router()

# --- Состояния для поиска выгодных предложений ---
class FindDealsStates(StatesGroup):
    waiting_for_query = State()
    waiting_for_pages = State()

main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Спарсить товар")]],
    resize_keyboard=True,
    input_field_placeholder="Отправьте ссылку или нажмите кнопку"
)

async def _send_formatted_product_message(message: Message, product_data: dict, product_url: str, deal_alert_prefix: str = ""):
    """Вспомогательная функция для форматирования и отправки сообщения о товаре."""
    current_price = product_data.get('current_price', 0.0)
    second_price = product_data.get('second_price', 0.0)
    feedback_discount = product_data.get('feedback_discount', 0.0)

    price_info = f"<b>Цена:</b> {current_price} ₽\n"
    if second_price > 0 and abs(second_price - current_price) > 0.01:
        price_info += f"<b>Обычная цена:</b> {second_price} ₽\n"
    if feedback_discount > 0:
        price_info += f"<b>Скидка за отзыв:</b> {feedback_discount} ₽\n"

    response_text = (
        f"{deal_alert_prefix}"
        f"<b>Название:</b> {product_data.get('product_name', 'Не найдено')}\n"
        f"{price_info}"
        f"<b>Бренд:</b> {product_data.get('brand', 'Не найден')}\n"
        f"<b>Рейтинг:</b> {product_data.get('rating', 0.0)} ({product_data.get('reviews', 0)} отзывов)\n"
        f"<a href='{product_url}'>Ссылка на товар</a>"
    )

    if product_data.get("images"):
        try:
            image_url = product_data["images"][0]
            await message.answer_photo(photo=URLInputFile(image_url), caption=response_text, parse_mode="HTML")
        except Exception as e:
            log_error(f"Ошибка отправки фото для {product_url}: {e}")
            await message.answer(response_text, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await message.answer(response_text, parse_mode="HTML", disable_web_page_preview=True)


@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(MSG_GREETING, reply_markup=main_kb)

@router.message(F.text == "Спарсить товар")
async def ask_link(message: Message):
    await message.answer(MSG_ASK_LINK)

@router.message(F.text.regexp(WB_URL_REGEX))
async def process_link(message: Message):
    url = message.text
    processing_message = await message.answer(MSG_PARSING_STARTED.format(url=url))
    log_info(f"Получена ссылка от пользователя {message.from_user.id}: {url}")

    driver_instance = None
    try:
        def run_parser_sync(u):
            nonlocal driver_instance
            try:
                driver_instance = get_driver()
                if not driver_instance: return {"status": "driver_init_error", "url": u}
                data = parse_product_page(driver_instance, u)
                return data
            finally:
                if driver_instance:
                    driver_instance.quit()
                    driver_instance = None
        
        data = await asyncio.to_thread(run_parser_sync, url)

        if data and data.get("product_name"):
            deal_alert_text = ""
            current_price = data.get('current_price', 0.0)
            feedback_discount = data.get('feedback_discount', 0.0)
            if feedback_discount > 0 and current_price > 0 and current_price < feedback_discount:
                deal_alert_text = DEAL_ALERT_PREFIX
            await _send_formatted_product_message(message, data, url, deal_alert_text)
        
        elif data and data.get("status") == "captcha_detected":
             await message.answer(MSG_CAPTCHA_DETECTED.format(url=url))
        elif data and data.get("status") == "parse_error":
            await message.answer(MSG_PARSE_ERROR_DEBUG_HTML.format(url=url, message=data.get('message', '')))
        elif data and data.get("status") == "product_unavailable":
            await message.answer(MSG_PRODUCT_UNAVAILABLE.format(url=url, message=data.get('message', '')))
        elif data and data.get("status") == "essential_data_missing":
            await message.answer(MSG_ESSENTIAL_DATA_MISSING.format(url=url, message=data.get('message', '')))
        elif data and data.get("status") == "driver_init_error":
            await message.answer(MSG_DRIVER_INIT_FAILED_FOR_ITEMS) # Используем общий месседж
        else:
            await message.answer(MSG_DATA_NOT_FOUND.format(url=url))
            log_error(f"Не удалось получить данные для {url}. Результат парсера: {data}")

    except Exception as e:
        log_error(f"Критическая ошибка при обработке ссылки {url} в боте: {type(e).__name__} - {e}")
        await message.answer(MSG_CRITICAL_ERROR_PROCESSING_LINK.format(url=url))
    finally:
        if processing_message:
            try:
                await processing_message.delete()
            except Exception:
                pass
        if driver_instance: # На всякий случай, если в run_parser_sync что-то пошло не так до finally
            log_warning(f"Драйвер для одиночной ссылки {url} не был корректно закрыт в потоке. Закрываю принудительно.")
            driver_instance.quit()

# --- Логика для /find_deals с параллельным парсингом ---
async def parse_item_worker(product_url: str, message: Message, semaphore: asyncio.Semaphore) -> dict:
    """Рабочая функция для парсинга одного URL. Управляет своим драйвером."""
    async with semaphore: # Ограничиваем количество одновременно запущенных драйверов
        log_processed_item(f"Worker: Начало обработки URL: {product_url}")
        driver = None
        data = None
        try:
            # Синхронные операции get_driver и parse_product_page выполняем в потоке
            def sync_parse_operations(url_to_parse):
                d = get_driver()
                if not d:
                    log_error(f"Worker: Не удалось инициализировать драйвер для {url_to_parse}")
                    return {"status": "driver_init_error", "url": url_to_parse, "product_name": None}
                try:
                    parsed_data = parse_product_page(d, url_to_parse)
                    return parsed_data
                finally:
                    d.quit()
            
            data = await asyncio.to_thread(sync_parse_operations, product_url)

            if data and data.get("product_name"):
                log_processed_item(f"Worker: Успешно {product_url} - {data.get('product_name')}")
                current_price = data.get('current_price', 0.0)
                feedback_discount = data.get('feedback_discount', 0.0)
                is_deal = feedback_discount > 0 and current_price > 0 and current_price < feedback_discount
                if is_deal:
                    await _send_formatted_product_message(message, data, product_url, DEAL_ALERT_PREFIX)
                return {"status": "success", "is_deal": is_deal, "processed": True}
            
            elif data:
                status = data.get("status", "unknown_error")
                err_msg = data.get("message", "")
                log_warning(f"Worker: Проблема с {product_url}. Статус: {status}. Сообщение: {err_msg}")
                log_processed_item(f"Worker: {status.capitalize()} {product_url} - {err_msg}")
                return {"status": status, "is_deal": False, "processed": True} # Считаем обработанным, даже если ошибка парсинга
            else:
                # Этого не должно происходить, если sync_parse_operations всегда возвращает dict
                log_error(f"Worker: Нет данных от парсера для {product_url}")
                log_processed_item(f"Worker: Нет данных {product_url}")
                return {"status": "no_data_from_parser", "is_deal": False, "processed": True}

        except Exception as e_worker:
            log_error(f"Worker: Критическая ошибка при обработке {product_url}: {type(e_worker).__name__} - {e_worker}")
            log_processed_item(f"Worker: Крит. ошибка {product_url} - {type(e_worker).__name__}")
            return {"status": "worker_critical_error", "is_deal": False, "processed": False} # Не считаем обработанным при крит. ошибке worker-а
        finally:
            log_processed_item(f"Worker: Завершение обработки URL: {product_url}")
            # Драйвер закрывается внутри sync_parse_operations

@router.message(Command("find_deals"))
async def cmd_find_deals_start(message: Message, state: FSMContext):
    await message.answer(MSG_ASK_SEARCH_QUERY)
    await state.set_state(FindDealsStates.waiting_for_query)

@router.message(FindDealsStates.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    search_query = message.text.strip()
    if not search_query:
        await message.answer(MSG_EMPTY_SEARCH_QUERY)
        return
    await state.update_data(search_query=search_query)
    await message.answer(MSG_ASK_NUM_PAGES)
    await state.set_state(FindDealsStates.waiting_for_pages)

@router.message(FindDealsStates.waiting_for_pages)
async def process_num_pages_and_search(message: Message, state: FSMContext):
    try:
        num_pages_to_check = int(message.text.strip())
        if num_pages_to_check <= 0:
            await message.answer(MSG_INVALID_NUM_PAGES_POSITIVE)
            return
    except ValueError:
        await message.answer(MSG_INVALID_NUM_PAGES_FORMAT)
        return

    user_data = await state.get_data()
    search_query = user_data.get("search_query")
    await state.clear()

    # Сначала получаем ссылки, это все еще последовательная операция с одним драйвером
    await message.answer(MSG_SEARCH_STARTED.format(search_query=search_query, num_pages_to_check=num_pages_to_check))
    links_driver_instance = None
    product_links = []
    try:
        def get_links_threaded_sync(query, num_pages):
            nonlocal links_driver_instance
            try:
                log_info(f"Запускаю get_driver для get_product_links с запросом: {query}")
                links_driver_instance = get_driver()
                if not links_driver_instance:
                    log_error("Не удалось создать драйвер для получения ссылок.")
                    return [] # Возвращаем пустой список, чтобы обработка ошибки произошла ниже
                found_links = get_product_links(links_driver_instance, search_query=query, max_pages=num_pages)
                log_info(f"get_product_links завершен, найдено ссылок: {len(found_links)}")
                return found_links
            finally:
                if links_driver_instance:
                    log_info("Закрываю драйвер после get_product_links.")
                    links_driver_instance.quit()
                    links_driver_instance = None
        
        product_links = await asyncio.to_thread(get_links_threaded_sync, search_query, num_pages_to_check)

    except Exception as e:
        log_error(f"Ошибка при получении списка ссылок для '{search_query}': {type(e).__name__} - {e}")
        await message.answer(MSG_ERROR_GETTING_LINKS)
        return # Выход, если ссылки не получены
    
    if not product_links:
        await message.answer(MSG_NO_LINKS_FOUND.format(search_query=search_query))
        return

    log_info(f"Найдено {len(product_links)} ссылок по запросу '{search_query}'. Первые 10: {product_links[:10]}")
    await message.answer(MSG_SEARCH_STARTED_PARALLEL.format(search_query=search_query, num_pages_to_check=num_pages_to_check, worker_count=MAX_CONCURRENT_PARSERS, link_count=len(product_links)))
    
    deals_found_count = 0
    processed_items_count = 0
    tasks = []
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PARSERS)

    for product_url in product_links:
        task = parse_item_worker(product_url, message, semaphore)
        tasks.append(task)
    
    results = []
    try:
        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks)
    except Exception as e_gather:
        log_error(f"Произошла ошибка во время выполнения asyncio.gather: {e_gather}")
        await message.answer("Во время параллельной обработки товаров произошла критическая ошибка.")

    # Подсчет результатов
    for res in results:
        if res and res.get("processed"):
            processed_items_count += 1
        if res and res.get("is_deal"):
            deals_found_count += 1
            
    log_info(f"Параллельный поиск завершен. Итого обработано: {processed_items_count}, найдено выгодных: {deals_found_count} из {len(product_links)} ссылок.")
    await message.answer(MSG_SEARCH_COMPLETED.format(processed=processed_items_count, total_links=len(product_links), deals_count=deals_found_count)) 