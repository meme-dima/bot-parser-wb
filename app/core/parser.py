# ... существующий код parser.py ... 

import time
import random
import requests
import re # Импортируем re для скидки за отзыв
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from .utils import get_random_user_agent, get_random_proxy, log_info, log_error, log_warning # ИЗМЕНЕН ИМПОРТ
from .config import DEFAULT_MAX_PAGES # ИЗМЕНЕН ИМПОРТ
from urllib.parse import urljoin, urlencode # Добавляем urlencode
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# Сбор ссылок с поисковой выдачи или категории

def get_product_links(driver, search_query=None, category_url=None, max_pages=DEFAULT_MAX_PAGES, min_price_rub=None, max_price_rub=None):
    links = set()
    base_url_wb = "https://www.wildberries.ru/"

    price_params = ""
    # Формируем параметр priceU, если указаны цены
    # Минимальная цена 0 копеек, если не указана
    min_kopecks = int(min_price_rub * 100) if min_price_rub is not None and min_price_rub >= 0 else 0
    # Максимальная цена ~20 млн руб (в копейках), если не указана или некорректна
    max_kopecks = int(max_price_rub * 100) if max_price_rub is not None and max_price_rub > 0 else 2000000000 
    
    if min_kopecks > max_kopecks : # Если вдруг минимальная стала больше максимальной (например, макс не указана, а мин большая)
        max_kopecks = min_kopecks + 10000 # Делаем макс чуть больше мин, или можно выбрать другую логику

    # Параметр priceU добавляется всегда, используя вычисленные min_kopecks и max_kopecks
    # %3B это точка с запятой для URL
    price_params = f"&priceU={min_kopecks}%3B{max_kopecks}"
    feedback_filter = "&ffeedbackpoints=1" # Используем фильтр "Рубли за отзыв"

    for page in range(1, max_pages + 1):
        current_page_url = ""
        if category_url:
            # Для URL категории, добавляем page, priceU и фильтр. Учитываем, что category_url может уже иметь параметры.
            separator = '&' if '?' in category_url else '?'
            current_page_url = f"{category_url}{separator}page={page}{price_params}{feedback_filter}"
        elif search_query:
            # Для поискового запроса, добавляем сортировку по популярности и фильтр
            current_page_url = f"https://www.wildberries.ru/catalog/0/search.aspx?page={page}&sort=popular&search={search_query}{price_params}{feedback_filter}"
        else:
            log_warning("get_product_links вызван без search_query и category_url.")
            break # Невозможно сформировать URL
        
        if page > 1:
            time.sleep(random.uniform(0.2, 0.5))
        log_info(f"Загружаю страницу: {current_page_url}")
        try:
            driver.get(current_page_url)
            WebDriverWait(driver, 10).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".product-card__wrapper")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".product-card")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".j-card-item")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".search-product-card")) 
                )
            )
        except TimeoutException:
            log_error(f"Timeout при загрузке страницы: {current_page_url}")
            continue
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for a in soup.find_all("a", href=True):
            if "/catalog/" in a["href"] and "/detail.aspx" in a["href"]:
                href_part = a["href"].split("?")[0]
                full_url = urljoin(base_url_wb, href_part)
                links.add(full_url)
    return list(links)

# Парсинг карточки товара

def parse_product_page(driver, url):
    log_info(f"Начинаю парсинг URL: {url}") # Логирование начала парсинга URL
    driver.get(url)
    time.sleep(random.uniform(1.0, 2.0)) # INCREASED delay back to 1.0-2.0 seconds
    page_source = driver.page_source
    soup = BeautifulSoup(page_source, "html.parser")
    
    debug_file_path = "app/data/debug_wb.html"
    try:
        with open(debug_file_path, 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        # log_info(f"Debug HTML сохранен в {debug_file_path} для URL: {url}") # Можно закомментировать, чтобы не спамить в лог
    except Exception as e:
        log_error(f"Ошибка сохранения debug HTML для {url}: {e}")

    if soup.find("div", class_="captcha__container") or "капча" in page_source.lower() or "captcha" in page_source.lower():
        log_warning(f"Обнаружена капча на странице: {url}") # Изменено на warning, т.к. это не ошибка парсера
        return {"status": "captcha_detected", "url": url}

    article_match = re.search(r"/catalog/(\d+)/detail.aspx", url)
    article = article_match.group(1) if article_match else ""
    
    h1 = soup.find("h1", class_=lambda x: x != 'popup__title')
    product_name = h1.text.strip() if h1 else ""
    
    if not product_name:
        log_warning(f"Название товара не найдено для URL: {url}. Проверьте селектор h1.")
        # Проверим, есть ли сообщение о том, что товар не найден или распродан
        not_found_selectors = [
            ".product-page__title--not-found",
            ".product-page__title-status--sold-out",
            "div.soldout-title > h1",
            ".empty-state-page__title",
            ".error-page__title"
        ]
        for selector in not_found_selectors:
            not_found_el = soup.select_one(selector)
            if not_found_el:
                message = not_found_el.text.strip()
                log_warning(f"Страница для {url} сообщает: '{message}'. Товар отсутствует или распродан.")
                return {"status": "product_unavailable", "message": message, "url": url}

    price_wb_wallet_val = 0.0
    price_normal_current_val = 0.0
    original_price_val = 0.0
    final_current_price = 0.0
    final_second_price = 0.0

    def clean_and_convert_price(price_str):
        if not price_str: return 0.0
        cleaned = "".join(filter(lambda char: char.isdigit() or char == '.' or char == ',', price_str))
        cleaned = cleaned.replace(",", ".")
        parts = cleaned.split('.')
        if len(parts) > 2:
            if len(parts[-1]) <= 2:
                cleaned = "".join(parts[:-1]) + "." + parts[-1]
            else:
                cleaned = "".join(parts)
        elif not parts:
             return 0.0
        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    wallet_price_selectors = [
        "span.price-block__wallet-price", 
        ".price-block__price-with-discount .price__value", 
        "div[class*='wallet-price'] span[class*='price__value']",
        "div[class*='wallet-price'] .price__active",
        "div[class*='wallet-price'] .price__lower-price"
    ]
    for selector in wallet_price_selectors:
        wallet_price_el = soup.select_one(selector)
        if wallet_price_el:
            if wallet_price_el.find_parent(['del', 's']): continue
            price_wb_wallet_val = clean_and_convert_price(wallet_price_el.get_text(strip=True))
            if price_wb_wallet_val > 0: break
        
    if price_wb_wallet_val == 0.0:
        wallet_text_node = soup.find(string=lambda t: t and "с wb кошельком" in t.lower())
        if wallet_text_node:
            parent_container = wallet_text_node.find_parent(lambda tag: tag.name in ['div', 'span'] and any(c.isdigit() for c in tag.get_text(strip=True)) and "₽" in tag.get_text(strip=True), limit=3)
            if parent_container:
                price_candidates_text = parent_container.find_all(string=re.compile(r'\d+'))
                for cand_text in price_candidates_text:
                    if "₽" in cand_text and not cand_text.find_parent(['del', 's']):
                        price_wb_wallet_val = clean_and_convert_price(cand_text)
                        if price_wb_wallet_val > 0: break

    price_block_content = soup.select_one(".product-page__price-block .price-block__content-bottom, .price-block__content-bottom")
    search_area_normal_price = price_block_content if price_block_content else soup

    normal_price_selectors = [
        "ins.price-block__final-price", "span.price-block__final-price",
        ".price-block__price:not([class*='old']):not([class*='wallet']) .price__active",
        ".price-block__price:not([class*='old']):not([class*='wallet']) .price__lower-price",
        "div.price-block__price > span.price-block__price-value:not(:has(del))"
    ]
    for selector in normal_price_selectors:
        el = search_area_normal_price.select_one(selector)
        if el:
            if el.find_parent(['del', 's']): continue
            temp_price = clean_and_convert_price(el.get_text(strip=True))
            if price_wb_wallet_val > 0 and abs(temp_price - price_wb_wallet_val) < 0.01:
                continue
            if temp_price > 0:
                price_normal_current_val = temp_price
                break

    if price_normal_current_val == 0.0:
        all_price_strings = search_area_normal_price.find_all(string=re.compile(r'\d+\s*₽'))
        for price_str_node in all_price_strings:
            if not price_str_node.find_parent(['del', 's']) and not price_str_node.find_parent(class_=[lambda c: c and 'wallet' in c, "price-block__price-with-discount", "price-block__old-price"]):
                temp_price = clean_and_convert_price(price_str_node)
                if price_wb_wallet_val > 0 and abs(temp_price - price_wb_wallet_val) < 0.01:
                    continue
                if temp_price > 0:
                    price_normal_current_val = temp_price
                    break

    original_price_selectors = ["del.price-block__old-price", "s.price-block__old-price", "del.price__old-price", "del.price--old"]
    for selector in original_price_selectors:
        el = soup.select_one(selector)
        if el:
            original_price_val = clean_and_convert_price(el.get_text(strip=True))
            if original_price_val > 0: break

    if price_wb_wallet_val > 0:
        final_current_price = price_wb_wallet_val
        if price_normal_current_val > 0 and abs(price_normal_current_val - price_wb_wallet_val) > 0.01:
            final_second_price = price_normal_current_val
        elif final_second_price == 0.0 and original_price_val > price_wb_wallet_val:
             pass 
    elif price_normal_current_val > 0: 
        final_current_price = price_normal_current_val
    
    if original_price_val > 0 and final_current_price > 0 and original_price_val <= final_current_price: original_price_val = 0.0
    if final_second_price > 0 and final_current_price > 0 and final_second_price <= final_current_price: final_second_price = 0.0

    if not product_name and final_current_price == 0.0:
        log_warning(f"Ключевые данные (название и цена) не найдены для URL: {url}. HTML сохранен в debug_wb.html")
        return {"status": "essential_data_missing", "message": "Product name and price not found", "url": url}
    elif not product_name: # Цена есть, названия нет
        log_warning(f"Название товара не найдено, но цена ({final_current_price}) есть для URL: {url}. HTML сохранен в debug_wb.html")
        # Решаем, возвращать ли такой товар. Пока вернем как есть, но без названия он не будет обработан в хендлере.
        # Можно вернуть: {"status": "product_name_missing", "message": "Product name not found but price exists", "url": url}
        # Но это потребует обработки нового статуса в handlers.py. Пока оставим так.
        pass # Данные будут возвращены ниже, но product_name будет пуст
    elif final_current_price == 0.0:
        log_warning(f"Цена не найдена (0.0) для товара '{product_name}' ({url}). HTML сохранен в debug_wb.html")
        # Можно добавить статус типа "price_not_found", но для простоты пока оставим, 
        # хендлер отфильтрует по цене > 0 если нужно для сделок.
        pass

    feedback_discount_val = 0.0
    feedback_el = soup.select_one("span.feedbacks-points-sum")
    if feedback_el:
        feedback_discount_val = clean_and_convert_price(feedback_el.get_text(strip=True))
    
    if feedback_discount_val == 0.0: 
        feedback_tags = soup.find_all(string=re.compile(r'(\d+)\s*(₽|руб).*?(за|на)\s+отзыв', re.IGNORECASE))
        if not feedback_tags: 
            feedback_tags_general = soup.find_all(string=lambda t: t and "₽ за отзыв" in t.lower() or "руб. за отзыв" in t.lower())
            for tag_text in feedback_tags_general:
                match = re.search(r'(\d[\d\s]*)\s*₽', tag_text, re.IGNORECASE)
                if not match: match = re.search(r'(\d[\d\s]*)\s*руб', tag_text, re.IGNORECASE)
                if match:
                    try: 
                        feedback_discount_val = float(match.group(1).replace(" ", ""))
                        if feedback_discount_val > 0: break
                    except ValueError: pass
        else: 
            for tag_text in feedback_tags:
                match = re.search(r'(\d[\d\s]*)\s*(?:₽|руб)', tag_text, re.IGNORECASE) 
                if match:
                    try: 
                        feedback_discount_val = float(match.group(1).replace(" ", ""))
                        if feedback_discount_val > 0: break
                    except ValueError: pass

    rating = 0.0
    rating_tag = soup.find("span", string=lambda t: t and ("оценок" in t or "оценка" in t or "отзывов" in t))
    if rating_tag and rating_tag.find_previous_sibling("span", class_=lambda c: c and 'star' in c):
         rating_value_element = rating_tag.find_previous_sibling("span", class_=lambda c: c and 'star' in c)
         if rating_value_element:
            try: rating = float(rating_value_element.text.replace(",", ".").strip())
            except: pass
    elif rating_tag: 
        try:
            rating_parent = rating_tag.find_previous("span")
            if rating_parent:
                rating = float(rating_parent.text.replace(",", "."))
        except: pass
    reviews = 0
    if rating_tag:
        try:
            reviews_text = rating_tag.get_text(strip=True).split()[0]
            reviews = int("".join(filter(str.isdigit, reviews_text)))
        except: pass
    brand = ""
    brand_link = soup.find("a", {"data-wba-brand-name": True})
    if brand_link:
        brand = brand_link.get("data-wba-brand-name")
    else: 
        brand_tag = soup.find("a", class_=lambda c: c and "brand" in c)
        if not brand_tag:
            brand_tag_original = soup.find("span", string="Оригинал")
            if brand_tag_original:
                brand_tag_previous = brand_tag_original.find_previous("span") 
                if brand_tag_previous:
                     brand = brand_tag_previous.text.strip()
        else:
            brand = brand_tag.text.strip()
    images = []
    page_base_url = url # Используем URL страницы как базу для относительных путей изображений

    main_image_selector = 'img.photo-zoom__preview, img.j-zoom-image'
    main_img_tag = soup.select_one(main_image_selector)
    if main_img_tag:
        main_img_src = main_img_tag.get('src')
        if main_img_src:
            resolved_main_img = urljoin(page_base_url, main_img_src)
            if resolved_main_img not in images:
                images.append(resolved_main_img)

    gallery_selectors = [".swiper-slide img[src]", ".img-plug img[src]", ".pv__img img[src]"]
    for selector in gallery_selectors:
        if len(images) >= 5: break
        for img_tag in soup.select(selector):
            if len(images) >= 5: break
            gallery_src = img_tag.get('src')
            if gallery_src:
                resolved_gallery_img = urljoin(page_base_url, gallery_src)
                if resolved_gallery_img not in images:
                    images.append(resolved_gallery_img)
    
    if len(images) < 5 and page_source: # Ищем в JSON-LD, если мало изображений
        try:
            script_tags = soup.find_all('script', type='application/ld+json')
            for script in script_tags:
                if len(images) >= 5: break
                import json # Импорт здесь, т.к. используется редко
                json_data = json.loads(script.string)
                if json_data.get('@type') == 'Product' and json_data.get('image'):
                    img_candidates = json_data['image']
                    if isinstance(img_candidates, list):
                        for img_url_candidate in img_candidates:
                            if len(images) >= 5: break
                            if isinstance(img_url_candidate, str):
                                resolved_json_img = urljoin(page_base_url, img_url_candidate)
                                if resolved_json_img not in images:
                                    images.append(resolved_json_img)
                    elif isinstance(img_candidates, str):
                         resolved_json_img = urljoin(page_base_url, img_candidates)
                         if resolved_json_img not in images and len(images) < 5:
                             images.append(resolved_json_img)
        except Exception as e:
            log_warning(f"Ошибка при парсинге изображений из JSON-LD для {url}: {e}")

    data = {
        "product_name": product_name,
        "current_price": final_current_price,
        "second_price": final_second_price, # Это будет или "обычная" текущая цена, или зачеркнутая, если "обычной" нет и она > цены кошелька
        "original_price": original_price_val, # Это всегда зачеркнутая цена, если она есть и > текущей
        "feedback_discount": feedback_discount_val,
        "rating": rating,
        "reviews": reviews,
        "brand": brand,
        "images": images,
        "article": article,
        "url": url
    }

    if not product_name and final_current_price == 0.0: # Повторная проверка, т.к. product_name мог быть найден, но цена нет
        # Это условие уже было выше, но оставим для ясности, что если дошли сюда и все еще нет ключевых данных
        log_warning(f"Возврат с essential_data_missing для {url}. Данные: {data}")
        # Статус essential_data_missing уже установлен выше, если это условие выполнилось там
        # Если product_name был, а цены нет, то верхний блок if not product_name and final_current_price == 0.0 не сработал бы
        # поэтому здесь мы можем уточнить, что если цена = 0, то это тоже проблема.
        if data.get("status") != "essential_data_missing": # Если статус не был установлен ранее
             return {"status": "essential_data_missing", "message": "Product name or price is zero after parsing", "url": url}
    
    log_info(f"Завершение парсинга для {url}. Найдено название: '{bool(product_name)}', цена: {final_current_price}")
    return data

# Получение Selenium driver с прокси и User-Agent

def get_driver(proxy=None, user_agent=None):
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=" + (user_agent if user_agent else get_random_user_agent()))
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2}) # Disable images
    # options.add_argument("--window-size=1920x1080")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    # if proxy:
    #     options.add_argument(f"--proxy-server={proxy}")

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        log_error(f"Ошибка инициализации драйвера: {e}")
        # Попытка использовать уже скачанный драйвер, если webdriver_manager не сработал
        try:
            log_info("Попытка использовать chromedriver из PATH, если он доступен")
            driver = webdriver.Chrome(options=options)
        except Exception as e_fallback:
            log_error(f"Ошибка инициализации драйвера (fallback): {e_fallback}")
            return None
    # Изменение User-Agent через CDP
    try:
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": options.arguments[-1].split('=',1)[1]})
    except Exception as e:
        log_warning(f"Не удалось изменить User-Agent через CDP: {e}")

    return driver 