import time
import random
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from utils import get_random_user_agent, get_random_proxy, log_info, log_error, load_cookies
from config import DEFAULT_MAX_PAGES

def get_product_links(driver, search_query=None, category_url=None, max_pages=DEFAULT_MAX_PAGES):
    links = set()
    for page in range(1, max_pages + 1):
        if category_url:
            url = f"{category_url}?page={page}"
        else:
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?page={page}&search={search_query}"
        driver.get(url)
        time.sleep(random.uniform(2, 4))
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for a in soup.find_all("a", href=True):
            if "/catalog/" in a["href"] and "/detail.aspx" in a["href"]:
                full_url = "https://www.wildberries.ru" + a["href"].split("?")[0]
                links.add(full_url)
    return list(links)

def get_all_product_links(driver, search_query=None, category_url=None):
    links = set()
    page = 1
    while True:
        if category_url:
            url = f"{category_url}?page={page}"
        else:
            url = f"https://www.wildberries.ru/catalog/0/search.aspx?page={page}&search={search_query}"
        driver.get(url)
        time.sleep(random.uniform(2, 4))
        soup = BeautifulSoup(driver.page_source, "html.parser")
        new_links = set()
        for a in soup.find_all("a", href=True):
            if "/catalog/" in a["href"] and "/detail.aspx" in a["href"]:
                full_url = "https://www.wildberries.ru" + a["href"].split("?")[0]
                new_links.add(full_url)
        if not new_links or new_links.issubset(links):
            break
        links.update(new_links)
        print(f"Собрано ссылок: {len(links)} (страница {page})")
        page += 1
    return list(links)

def parse_product_page(driver, url):
    driver.get(url)
    # Устанавливаем cookies, если есть
    cookies = load_cookies()
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except Exception:
            pass
    driver.get(url)  # Перезагружаем страницу с cookies
    time.sleep(random.uniform(2, 4))
    soup = BeautifulSoup(driver.page_source, "html.parser")
    if soup.find("div", class_="captcha__container"):
        input("Обнаружена капча! Решите вручную и нажмите Enter...")
        soup = BeautifulSoup(driver.page_source, "html.parser")
    article = url.split('/')[-2]
    product_name = soup.find("h1", {"data-link": "text{:productCard.title}"})
    product_name = product_name.text.strip() if product_name else ""
    price_block = soup.find("span", {"class": "price-block__final-price"})
    if not price_block:
        price_block = soup.find("ins", {"class": "price-block__price"})
    current_price = float(price_block.text.replace("₽", "").replace(" ", "").replace(",", ".").strip()) if price_block else 0.0
    feedback_discount = 0.0
    for el in soup.find_all("span"):
        if "за отзыв" in el.text:
            try:
                feedback_discount = float(el.text.split("₽")[0].replace(" ", "").replace(",", ".").strip())
                break
            except:
                continue
    rating = 0.0
    rating_tag = soup.find("span", class_="product-rating__count")
    if rating_tag:
        try:
            rating = float(rating_tag.text.replace(",", "."))
        except:
            pass
    reviews = 0
    reviews_tag = soup.find("span", class_="product-rating__amount")
    if reviews_tag:
        try:
            reviews = int(reviews_tag.text.strip())
        except:
            pass
    brand = ""
    brand_tag = soup.find("span", class_="product-params__cell")
    if brand_tag:
        brand = brand_tag.text.strip()
    images = []
    for img in soup.find_all("img", class_="slider__image"):
        images.append(img.get("src"))
    description = ""
    desc_tag = soup.find("p", class_="collapsable__text")
    if desc_tag:
        description = desc_tag.text.strip()
    composition = ""
    for row in soup.find_all("div", class_="product-params__row"):
        if "Состав" in row.text:
            composition = row.text.split(":")[-1].strip()
    return {
        "article": article,
        "product_name": product_name,
        "current_price": current_price,
        "feedback_discount": feedback_discount,
        "discount_difference": round(feedback_discount - current_price, 2),
        "url": url,
        "rating": rating,
        "reviews": reviews,
        "brand": brand,
        "images": images,
        "description": description,
        "composition": composition
    }

def get_driver(proxy=None, user_agent=None):
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    if proxy:
        options.add_argument(f'--proxy-server={proxy}')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver 