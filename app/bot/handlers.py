from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, URLInputFile, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.core.parser import get_driver, parse_product_page, get_product_links
from app.core.utils import log_info, log_error, log_warning, log_processed_item
from app.core.filters import is_matching_deal
import asyncio
import random

# --- Текстовые константы ---
MSG_GREETING = (
    "Привет! 👋 Я бот для парсинга Wildberries. 🤖\n"
    "Нажми кнопку «📄 Спарсить товар» или просто отправь мне ссылку на товар Wildberries.\n\n"
    "Или используй команду /find_deals для поиска выгодных предложений! 🔍"
)
MSG_ASK_LINK = "🔗 Пришли ссылку на товар Wildberries:"
MSG_PARSING_STARTED = "⚙️ Начинаю парсинг для: {url}\n⏳ Пожалуйста, подожди..."
MSG_ASK_SEARCH_QUERY = "🔍 Введите поисковый запрос (например, 'беспроводные наушники'):"
MSG_EMPTY_SEARCH_QUERY = "⚠️ Поисковый запрос не может быть пустым. Пожалуйста, введите запрос:"
MSG_ASK_MIN_PRICE = "💰 Введите минимальную цену (например, 0) или отправьте '-', чтобы пропустить:"
MSG_INVALID_MIN_PRICE_FORMAT = "❌ Минимальная цена должна быть числом. Попробуйте еще раз или отправьте '-' для пропуска:"
MSG_ASK_MAX_PRICE = "💰 Введите максимальную цену (например, 300) или отправьте '-', чтобы пропустить:"
MSG_INVALID_MAX_PRICE_FORMAT = "❌ Максимальная цена должна быть числом. Попробуйте еще раз или отправьте '-' для пропуска:"
MSG_MAX_PRICE_LESS_THAN_MIN = "📉 Максимальная цена не может быть меньше минимальной. Введите корректное значение или '-':"
MSG_ASK_NUM_PAGES = "📄 Сколько страниц поисковой выдачи проверить? (число, например, 3)"
MSG_INVALID_NUM_PAGES_POSITIVE = "❌ Количество страниц должно быть положительным числом. Попробуйте еще раз:"
MSG_INVALID_NUM_PAGES_FORMAT = "❌ Пожалуйста, введите корректное число страниц (например, 3):"
MSG_SEARCH_STARTED = "Начинаю поиск по запросу: '{search_query}' на {num_pages_to_check} страницах... Это может занять некоторое время."
MSG_NO_LINKS_FOUND = "🤷‍♂️ По запросу '{search_query}' ничего не найдено на указанном количестве страниц."
MSG_LINKS_FOUND_START_PROCESSING = "Найдено {count} товаров. Начинаю проверку на выгодные предложения..."
MSG_ITEMS_CHECKED_PROGRESS = "Проверено {checked} из {total} товаров..."
MSG_SEARCH_COMPLETED = "🎉 Поиск завершен!\nПроверено товаров: {processed} из {total_links}.\nНайдено выгодных предложений: {deals_count} 🏁"
MSG_CAPTCHA_DETECTED = "🛡️ Не удалось получить данные: обнаружена капча на странице {url}. Попробуйте позже."
MSG_PARSE_ERROR_DEBUG_HTML = "🐞 Не удалось полностью разобрать страницу для: {url}. Проверьте debug_wb.html. {message}"
MSG_DATA_NOT_FOUND = "❓ Не удалось получить данные для: {url}. Возможно, структура страницы изменилась или товар недоступен."
MSG_CRITICAL_ERROR_PROCESSING_LINK = "💥 Произошла критическая ошибка при обработке ссылки: {url}. Попробуйте позже."
MSG_ERROR_GETTING_LINKS = "🕸️ Не удалось получить список товаров для поиска. Попробуйте позже."
MSG_DRIVER_INIT_FAILED_FOR_ITEMS = "🚗❌ Не удалось инициализировать драйвер для проверки товаров. Поиск прерван."
MSG_ERROR_IN_ITEM_PROCESSING_LOOP = "🔄⚠️ Во время проверки товаров произошла ошибка. Поиск может быть неполным."
MSG_PRODUCT_UNAVAILABLE = "🚫 Товар по ссылке {url} недоступен (распродан/страница удалена). Сообщение: {message}"
MSG_ESSENTIAL_DATA_MISSING = "🧩 Не удалось извлечь ключевые данные (название/цена) для товара: {url}. {message}"

# Новые текстовые константы для статистики
MSG_SEARCH_PROCESSING_PROMPT = "⏳ Поиск запущен. Нажмите кнопку ниже для просмотра текущей статистики 👇"
BTN_SHOW_STATS = "📊 Статистика поиска"
BTN_STOP_SEARCH = "❌ Остановить поиск"
MSG_SEARCH_STOP_REQUESTED = "⏳ Попытка остановить поиск..."
MSG_SEARCH_STOPPED_BY_USER = "🛑 Поиск остановлен пользователем."
MSG_SEARCH_STATS_FORMAT = (
    "<b>📊 Статистика поиска:</b>\n\n"
    "🔍 Запрос: <code>{query}</code>\n"
    "💰 Цена: от {min_price} до {max_price}\n"
    "📄 Всего ссылок для проверки: {total_links}\n"
    "🔄 Проверено товаров: {processed_count} из {total_links}\n"
    "🔥 Найдено выгодных предложений: {deals_found}"
)
STATS_UNAVAILABLE = "ℹ️ Статистика поиска в данный момент недоступна или поиск уже завершен."

DEAL_ALERT_PREFIX = "🔥 <b>ВЫГОДНОЕ ПРЕДЛОЖЕНИЕ!</b> Цена ниже скидки за отзыв!\n"

# --- Константы для логики ---
WB_URL_REGEX = r"https://www\.wildberries\.ru/catalog/\d+/detail\.aspx"
# PROGRESS_UPDATE_INTERVAL = 10 # Больше не используется для сообщений в чат

router = Router()

# --- Состояния для поиска выгодных предложений ---
class FindDealsStates(StatesGroup):
    waiting_for_query = State()
    waiting_for_min_price = State()
    waiting_for_max_price = State()
    waiting_for_pages = State()
    processing_items = State() # Новое состояние для отображения статистики

# --- Константы для кнопок --- 
BTN_PARSE_SINGLE_ITEM = "📄 Спарсить товар"
BTN_FIND_DEALS_MAIN = "🔍 Найти выгодные товары"

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_PARSE_SINGLE_ITEM)],
        [KeyboardButton(text=BTN_FIND_DEALS_MAIN)] # Новая кнопка
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие"
)

# Клавиатура для отображения статистики и остановки
search_stats_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_SHOW_STATS)],
        [KeyboardButton(text=BTN_STOP_SEARCH)]
    ],
    resize_keyboard=True
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
async def cmd_start(message: Message, state: FSMContext): # Добавил state для единообразия, хотя он тут не используется
    # Если пользователь был в каком-то состоянии, очистим его при /start
    await state.clear()
    await message.answer(MSG_GREETING, reply_markup=main_kb)

@router.message(F.text == BTN_PARSE_SINGLE_ITEM) # Используем константу
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
        if driver_instance:
            log_warning(f"Драйвер не был закрыт в потоке для {url}. Закрываю принудительно.")
            driver_instance.quit()

# Обработчики для /find_deals и новой кнопки
@router.message(Command("find_deals"))
@router.message(F.text == BTN_FIND_DEALS_MAIN) # Новый обработчик для кнопки
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
    await message.answer(MSG_ASK_MIN_PRICE)
    await state.set_state(FindDealsStates.waiting_for_min_price)

@router.message(FindDealsStates.waiting_for_min_price)
async def process_min_price(message: Message, state: FSMContext):
    min_price_str = message.text.strip()
    min_price = None
    if min_price_str == '-':
        pass
    else:
        try:
            min_price = float(min_price_str)
            if min_price < 0:
                await message.answer(MSG_INVALID_MIN_PRICE_FORMAT)
                return
        except ValueError:
            await message.answer(MSG_INVALID_MIN_PRICE_FORMAT)
            return
    
    await state.update_data(min_price=min_price)
    await message.answer(MSG_ASK_MAX_PRICE)
    await state.set_state(FindDealsStates.waiting_for_max_price)

@router.message(FindDealsStates.waiting_for_max_price)
async def process_max_price(message: Message, state: FSMContext):
    max_price_str = message.text.strip()
    max_price = None
    user_data = await state.get_data()
    min_price = user_data.get('min_price')

    if max_price_str == '-':
        pass
    else:
        try:
            max_price = float(max_price_str)
            if max_price < 0:
                await message.answer(MSG_INVALID_MAX_PRICE_FORMAT)
                return
            if min_price is not None and max_price < min_price:
                await message.answer(MSG_MAX_PRICE_LESS_THAN_MIN)
                return
        except ValueError:
            await message.answer(MSG_INVALID_MAX_PRICE_FORMAT)
            return
            
    await state.update_data(max_price=max_price)
    await message.answer(MSG_ASK_NUM_PAGES)
    await state.set_state(FindDealsStates.waiting_for_pages)

@router.message(FindDealsStates.waiting_for_pages)
async def process_all_filters_and_search(message: Message, state: FSMContext):
    try:
        num_pages_to_check = int(message.text.strip())
        if num_pages_to_check <= 0:
            await message.answer(MSG_INVALID_NUM_PAGES_POSITIVE, reply_markup=main_kb)
            await state.clear()
            return
    except ValueError:
        await message.answer(MSG_INVALID_NUM_PAGES_FORMAT, reply_markup=main_kb)
        await state.clear()
        return

    user_data_for_search = await state.get_data()
    search_query = user_data_for_search.get("search_query")
    min_price = user_data_for_search.get("min_price")
    max_price = user_data_for_search.get("max_price")
    
    await state.clear() # Очищаем состояние после получения всех данных

    initial_message_text = (
        f"🚀 Начинаю поиск по запросу: '{search_query}'\\n"
        f"💰 Цена от: {'не указана' if min_price is None else min_price} до {'не указана' if max_price is None else max_price}\\n"
        f"📄 Проверка страниц: {num_pages_to_check}\\n\\n"
        "⏳ Это может занять некоторое время..."
    )
    await message.answer(initial_message_text)

    links_driver_instance = None
    product_links = []
    processed_items_count_local = 0
    deals_found_count_local = 0

    try:
        def get_links_threaded(query, num_pages, p_min, p_max):
            nonlocal links_driver_instance
            try:
                log_info(f"Запускаю get_driver для get_product_links с запросом: {query}, мин.цена: {p_min}, макс.цена: {p_max}")
                links_driver_instance = get_driver()
                log_info(f"Драйвер для get_product_links получен. Запускаю get_product_links.")
                found_links = get_product_links(links_driver_instance, 
                                                search_query=query, 
                                                max_pages=num_pages, 
                                                min_price_rub=p_min, 
                                                max_price_rub=p_max)
                log_info(f"get_product_links завершен, найдено ссылок: {len(found_links)}")
                return found_links
            finally:
                if links_driver_instance:
                    log_info("Закрываю драйвер после get_product_links.")
                    links_driver_instance.quit()
                    links_driver_instance = None
        
        product_links = await asyncio.to_thread(get_links_threaded, search_query, num_pages_to_check, min_price, max_price)
        log_info(f"Найдено {len(product_links)} ссылок по запросу '{search_query}' (с учетом фильтра цен priceU). Ссылки: {product_links if len(product_links) < 10 else str(product_links[:10]) + '...'}")

    except Exception as e:
        log_error(f"Ошибка при получении списка ссылок для '{search_query}': {type(e).__name__} - {e}")
        await message.answer(MSG_ERROR_GETTING_LINKS, reply_markup=main_kb)
        return # состояние уже очищено выше
    
    if not product_links:
        await message.answer(MSG_NO_LINKS_FOUND.format(search_query=search_query), reply_markup=main_kb)
        return # состояние уже очищено выше

    await state.set_state(FindDealsStates.processing_items)
    await state.update_data(
        search_query_for_stats=search_query,
        min_price_for_stats=min_price,
        max_price_for_stats=max_price,
        total_links_for_stats=len(product_links),
        processed_items_count_stats=0,
        deals_found_count_stats=0,
        cancel_requested=False # Флаг для отмены
    )
    await message.answer(MSG_SEARCH_PROCESSING_PROMPT, reply_markup=search_stats_kb)
    
    item_parser_driver_instance_main = None
    try:
        log_info(f"Создаю основной драйвер для цикла парсинга {len(product_links)} товаров.")
        item_parser_driver_instance_main = get_driver()
        if not item_parser_driver_instance_main:
            await message.answer(MSG_DRIVER_INIT_FAILED_FOR_ITEMS, reply_markup=main_kb)
            log_error("Не удалось создать основной драйвер для парсинга элементов.")
            current_fsm_state_init_fail = await state.get_state()
            if current_fsm_state_init_fail == FindDealsStates.processing_items.state: # Очищаем, если ошибка на этом этапе
                 await state.clear()
            return

        for i, product_url in enumerate(product_links):
            current_fsm_data = await state.get_data() # Получаем актуальные данные FSM
            if current_fsm_data.get("cancel_requested"):
                await message.answer(MSG_SEARCH_STOPPED_BY_USER, reply_markup=main_kb)
                break 

            log_processed_item(f"Начало обработки URL: {product_url}")
            try:
                def run_single_item_parser_sync_reuse_driver(driver_to_use, url_to_parse):
                    data = parse_product_page(driver_to_use, url_to_parse)
                    return data
                
                data = await asyncio.to_thread(run_single_item_parser_sync_reuse_driver, item_parser_driver_instance_main, product_url)
                processed_items_count_local += 1

                if data and data.get("product_name"):
                    log_processed_item(f"Успешно: {product_url} - {data.get('product_name')}")
                    if is_matching_deal(data, user_min_price=min_price, user_max_price=max_price): # Используем min_price, max_price из замыкания
                        deals_found_count_local += 1
                        await _send_formatted_product_message(message, data, product_url, DEAL_ALERT_PREFIX)
                elif data and data.get("status") == "captcha_detected": # Исправлена вложенность
                    log_warning(f"Капча при обработке {product_url} в цикле.")
                elif data and data.get("status") == "product_unavailable": # Исправлена вложенность
                    log_warning(f"Товар {product_url} недоступен в цикле: {data.get('message', '')}")
                elif data and data.get("status") == "essential_data_missing": # Исправлена вложенность
                    log_warning(f"Нет данных для {product_url} в цикле: {data.get('message', '')}")
                else: # Исправлена вложенность
                    log_warning(f"Не удалось получить данные для {product_url} в цикле. Результат: {data}")
                
                # Обновляем данные для статистики в FSM
                current_fsm_state_in_loop = await state.get_state() 
                if current_fsm_state_in_loop == FindDealsStates.processing_items.state:
                    await state.update_data(processed_items_count_stats=processed_items_count_local, deals_found_count_stats=deals_found_count_local)
                else: 
                    log_warning(f"Состояние FSM изменилось во время обработки ({current_fsm_state_in_loop}), прерываю поиск.")
                    await message.answer("Поиск был прерван из-за смены команды.", reply_markup=main_kb)
                    break
            except Exception as e_item:
                log_error(f"Ошибка в цикле обработки товара {product_url}: {type(e_item).__name__} - {e_item}")

    except Exception as e_main_loop:
        log_error(f"Главная ошибка в цикле проверки товаров: {type(e_main_loop).__name__} - {e_main_loop}")
        await message.answer(MSG_ERROR_IN_ITEM_PROCESSING_LOOP, reply_markup=main_kb)
        # Если была ошибка в основном цикле, состояние processing_items тоже надо очистить
        current_fsm_state_on_error = await state.get_state()
        if current_fsm_state_on_error == FindDealsStates.processing_items.state:
            await state.clear()
    finally:
        if item_parser_driver_instance_main:
            log_info("Закрываю основной драйвер после цикла парсинга.")
            item_parser_driver_instance_main.quit()
        
        await message.answer(
            MSG_SEARCH_COMPLETED.format(
                processed=processed_items_count_local, 
                total_links=len(product_links),
                deals_count=deals_found_count_local
            ),
            reply_markup=main_kb
        )
        current_fsm_state_finally = await state.get_state()
        if current_fsm_state_finally == FindDealsStates.processing_items.state:
            await state.clear()

# Обработчик для кнопки "Остановить поиск"
@router.message(FindDealsStates.processing_items, F.text == BTN_STOP_SEARCH)
async def cmd_stop_search(message: Message, state: FSMContext):
    await state.update_data(cancel_requested=True)
    await message.answer(MSG_SEARCH_STOP_REQUESTED, reply_markup=ReplyKeyboardRemove())

# Обработчик для кнопки статистики
@router.message(FindDealsStates.processing_items, F.text == BTN_SHOW_STATS)
async def show_search_stats(message: Message, state: FSMContext):
    stats_data = await state.get_data()
    if not stats_data or 'total_links_for_stats' not in stats_data:
        await message.answer(STATS_UNAVAILABLE, reply_markup=main_kb)
        current_fsm_state_no_data = await state.get_state()
        if current_fsm_state_no_data == FindDealsStates.processing_items.state:
            await state.clear()
        return

    query = stats_data.get('search_query_for_stats', 'неизвестно')
    min_p = stats_data.get('min_price_for_stats')
    max_p = stats_data.get('max_price_for_stats')
    total = stats_data.get('total_links_for_stats', 0)
    processed = stats_data.get('processed_items_count_stats', 0)
    deals = stats_data.get('deals_found_count_stats', 0)
    last_stats_message_id = stats_data.get('last_stats_message_id')

    min_p_str = str(min_p) if min_p is not None else 'не указана'
    max_p_str = str(max_p) if max_p is not None else 'не указана'

    text_to_send = MSG_SEARCH_STATS_FORMAT.format(
        query=query,
        min_price=min_p_str,
        max_price=max_p_str,
        total_links=total,
        processed_count=processed,
        deals_found=deals
    )

    try:
        if last_stats_message_id:
            await message.bot.edit_message_text(
                text=text_to_send,
                chat_id=message.chat.id,
                message_id=last_stats_message_id,
                parse_mode="HTML",
                reply_markup=search_stats_kb
            )
            # Если отредактировали, то исходное сообщение пользователя (нажатие кнопки) можно удалить, чтобы не было "лишнего"
            # await message.delete() # Раскомментировать, если нужно удалять сообщение с кнопкой
        else:
            sent_message = await message.answer(text_to_send, parse_mode="HTML", reply_markup=search_stats_kb)
            await state.update_data(last_stats_message_id=sent_message.message_id)
    except Exception as e: # Если редактирование не удалось (например, сообщение слишком старое или удалено)
        log_warning(f"Не удалось отредактировать сообщение статистики (ID: {last_stats_message_id}): {e}. Отправляю новое.")
        sent_message = await message.answer(text_to_send, parse_mode="HTML", reply_markup=search_stats_kb)
        await state.update_data(last_stats_message_id=sent_message.message_id)

# Убедимся, что router.include_router(other_router) или dp.include_router(router) есть в main.py или app.py 