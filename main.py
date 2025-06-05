import argparse
import sys
from app.core.parser import get_driver, parse_product_page
from app.core.filters import filter_product
from app.core.utils import get_random_user_agent, get_random_proxy, log_info, log_error
import json
import pandas as pd

def main():
    parser = argparse.ArgumentParser(description="Wildberries парсер (CLI)")
    parser.add_argument('--url', type=str, help='URL карточки товара для парсинга')
    parser.add_argument('--out-json', type=str, default='app/data/results.json', help='Файл для JSON')
    parser.add_argument('--out-csv', type=str, default='app/data/results.csv', help='Файл для CSV')
    args = parser.parse_args()

    if not args.url:
        print("Укажи ссылку через --url")
        sys.exit(1)

    driver = get_driver(get_random_proxy(), get_random_user_agent())
    data = parse_product_page(driver, args.url)
    driver.quit()
    if data:
        with open(args.out_json, 'w', encoding='utf-8') as f:
            json.dump([data], f, ensure_ascii=False, indent=2)
        pd.DataFrame([data]).to_csv(args.out_csv, index=False, encoding='utf-8-sig')
        print(f"Сохранено: {args.out_json}, {args.out_csv}")
    else:
        print("Не удалось спарсить товар.")

if __name__ == "__main__":
    main() 