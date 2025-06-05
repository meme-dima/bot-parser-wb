# WildBerriesParser

## Структура
- `app/core/` — логика парсинга
- `app/bot/` — Telegram-бот на aiogram v3
- `app/data/` — результаты, логи

## Запуск парсера (CLI)
```bash
python main.py --url <ссылка>
```

## Запуск Telegram-бота
1. Установи зависимости:
```bash
pip install -r requirements.txt
```
2. Укажи токен бота в переменной окружения `WB_BOT_TOKEN` или в файле `app/bot/main.py`.
3. Запусти:
```bash
python -m app.bot.main
```

## Требования
- Python 3.10+
- Google Chrome + chromedriver
- Aiogram v3

## Возможности бота
- Кнопка "Спарсить товар"
- Парсинг по ссылке Wildberries
- Ответ с названием, ценой, брендом, рейтингом, отзывами, составом и фото 