import json
import os
import subprocess
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
import asyncio
import time
import logging

USER_CONFIG = 'user_config.json'
PARSER_PROCESS_FILE = 'parser_process.pid'
PROGRESS_FILE = 'progress.json'

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Работа с конфигом ---
def load_user_config():
    if os.path.exists(USER_CONFIG):
        with open(USER_CONFIG, encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user_config(cfg):
    with open(USER_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def get_param(cfg, key, default=None):
    return cfg.get(key, default)

def set_param(cfg, key, value):
    cfg[key] = value
    save_user_config(cfg)

# --- Telegram-бот ---
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot)

# --- Управление процессом парсера ---
parser_proc = None

def is_parser_running():
    if os.path.exists(PARSER_PROCESS_FILE):
        try:
            with open(PARSER_PROCESS_FILE, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except Exception:
            os.remove(PARSER_PROCESS_FILE)
    return False

def save_parser_pid(pid):
    with open(PARSER_PROCESS_FILE, 'w') as f:
        f.write(str(pid))

def clear_parser_pid():
    if os.path.exists(PARSER_PROCESS_FILE):
        os.remove(PARSER_PROCESS_FILE)

async def send_file_if_exists(chat_id, filepath, caption=None):
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            await bot.send_document(chat_id, f, caption=caption)

async def send_progress_updates(chat_id):
    last_batch = -1
    while is_parser_running():
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, encoding='utf-8') as f:
                try:
                    prog = json.load(f)
                except Exception:
                    prog = None
            if prog and prog.get('batch_num', -1) != last_batch:
                last_batch = prog['batch_num']
                text = (
                    f"⏳ <b>Прогресс парсинга WB</b>\n"
                    f"Пакет: <b>{prog['batch_num']}/{prog['total_batches']}</b>\n"
                    f"Обработано ссылок: <b>{prog['total']}</b>\n"
                    f"Найдено подходящих: <b>{prog['found']}</b>\n"
                    f"Время работы: <b>{prog['work_time']:.1f} мин</b>\n"
                )
                await bot.send_message(chat_id, text, parse_mode='HTML')
        await asyncio.sleep(60)

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для управления WB-парсером.\nИспользуй /show для просмотра параметров, /set для изменения, /start_parsing для запуска.")

@dp.message_handler(commands=['show'])
async def cmd_show(message: types.Message):
    cfg = load_user_config()
    text = "<b>Текущие параметры:</b>\n"
    for k, v in cfg.items():
        text += f"<b>{k}</b>: {v}\n"
    await message.answer(text, parse_mode='HTML')

@dp.message_handler(commands=['set'])
async def cmd_set(message: types.Message):
    cfg = load_user_config()
    try:
        _, key, value = message.text.split(maxsplit=2)
        set_param(cfg, key, value)
        await message.answer(f"Параметр <b>{key}</b> установлен в <b>{value}</b>", parse_mode='HTML')
    except Exception:
        await message.answer("Используй: /set ключ значение\nНапример: /set min_price 100")

@dp.message_handler(commands=['toggle'])
async def cmd_toggle(message: types.Message):
    cfg = load_user_config()
    try:
        _, key = message.text.split(maxsplit=1)
        val = not bool(cfg.get(key, False))
        set_param(cfg, key, val)
        await message.answer(f"Параметр <b>{key}</b> переключён на <b>{val}</b>", parse_mode='HTML')
    except Exception:
        await message.answer("Используй: /toggle ключ\nНапример: /toggle enable_proxy")

@dp.message_handler(commands=['filters'])
async def cmd_filters(message: types.Message):
    cfg = load_user_config()
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Мин. цена", callback_data='set_min_price'),
        InlineKeyboardButton("Макс. цена", callback_data='set_max_price'),
        InlineKeyboardButton("Мин. рейтинг", callback_data='set_min_rating'),
        InlineKeyboardButton("Мин. отзывы", callback_data='set_min_reviews'),
        InlineKeyboardButton("Бренд", callback_data='set_brand'),
    )
    await message.answer("Выберите фильтр для изменения:", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith('set_'))
async def process_set_filter(callback_query: types.CallbackQuery):
    param = callback_query.data.replace('set_', '')
    await bot.send_message(callback_query.from_user.id, f"Введите новое значение для {param}:")
    @dp.message_handler()
    async def set_value(msg: types.Message):
        cfg = load_user_config()
        set_param(cfg, param, msg.text)
        await msg.answer(f"Параметр <b>{param}</b> установлен в <b>{msg.text}</b>", parse_mode='HTML')
        dp.message_handlers.unregister(set_value)

@dp.message_handler(commands=['start_parsing'])
async def cmd_start_parsing(message: types.Message):
    if is_parser_running():
        await message.answer("Парсер уже запущен! Дождитесь завершения или используйте /stop для отмены.")
        return
    cfg = load_user_config()
    await message.answer("Парсер запущен! Ожидайте отчёт...")
    logger.info(f"Запуск парсера для чата {message.chat.id} с параметрами: {cfg}")
    args = []
    for k, v in cfg.items():
        if isinstance(v, bool):
            if v:
                args.append(f"--{k}")
        else:
            args.append(f"--{k}")
            args.append(str(v))
    # Запуск задачи для отправки прогресса
    progress_task = asyncio.create_task(send_progress_updates(message.chat.id))
    try:
        proc = await asyncio.create_subprocess_exec(
            'python', 'main.py', *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        save_parser_pid(proc.pid)
        logger.info(f"Парсер запущен с PID: {proc.pid}")
        stdout, stderr = await proc.communicate()
        clear_parser_pid()
        progress_task.cancel()

        if stdout:
            logger.info(f"Stdout парсера: {stdout.decode()}")
        if stderr:
            logger.error(f"Stderr парсера: {stderr.decode()}")
        if proc.returncode != 0:
            await message.answer(f"Парсер завершился с ошибкой (код {proc.returncode}). Подробности в логах.")
            logger.error(f"Парсер завершился с кодом {proc.returncode}")
        else:
            await send_file_if_exists(message.chat.id, cfg.get('out_json', 'results.json'), caption="Результаты WB парсера (JSON)")
            await send_file_if_exists(message.chat.id, cfg.get('out_csv', 'results.csv'), caption="Результаты WB парсера (CSV)")
            await send_file_if_exists(message.chat.id, cfg.get('error_log', 'errors.log'), caption="Лог ошибок WB парсера")
            await message.answer("Парсинг завершён! Итоги и файлы отправлены.")
            logger.info("Парсинг успешно завершен.")

    except FileNotFoundError:
        logger.error("Ошибка: main.py не найден. Невозможно запустить парсер.")
        await message.answer("Ошибка: `main.py` не найден. Проверьте структуру проекта.")
        clear_parser_pid() # На всякий случай, если PID был создан до ошибки
        progress_task.cancel() # Отменяем задачу прогресса
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске или работе парсера: {e}", exc_info=True)
        await message.answer(f"Произошла критическая ошибка при работе парсера. Подробности в логах.")
        clear_parser_pid()
        progress_task.cancel()

@dp.message_handler(commands=['stop'])
async def cmd_stop(message: types.Message):
    if not is_parser_running():
        await message.answer("Парсер не запущен.")
        return
    try:
        with open(PARSER_PROCESS_FILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 9) # Используем SIGKILL для немедленной остановки
        clear_parser_pid()
        await message.answer("Парсер остановлен.")
        logger.info(f"Парсер с PID {pid} был остановлен по команде.")
    except ProcessLookupError:
        await message.answer("Процесс парсера не найден. Возможно, он уже был остановлен.")
        logger.warning(f"Попытка остановить несуществующий процесс парсера (PID: {pid}).")
        clear_parser_pid() # Очищаем PID файл, если процесс не найден
    except Exception as e:
        await message.answer(f"Ошибка при остановке парсера: {e}")
        logger.error(f"Ошибка при остановке парсера: {e}", exc_info=True)

if __name__ == '__main__':
    logger.info("Бот запускается...")
    executor.start_polling(dp, skip_updates=True) 