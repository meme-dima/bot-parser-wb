import json
import os
import subprocess
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
import asyncio
import time
from aiogram.filters import Command
from aiogram import Router
from aiogram.types import CallbackQuery
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

USER_CONFIG = 'user_config.json'
PARSER_PROCESS_FILE = 'parser_process.pid'
PROGRESS_FILE = 'progress.json'

PARAMS_HELP = (
    "<b>Доступные параметры для настройки:</b>\n"
    "🔑 <b>search</b> — Ключевое слово для поиска (пример: маска для волос)\n"
    "🔗 <b>category</b> — URL категории Wildberries\n"
    "📄 <b>update_articles</b> — Файл со списком артикулов для обновления цен\n"
    "🎲 <b>random</b> — Сколько случайных товаров проверить\n"
    "📄 <b>all_pages</b> — Максимальный сбор (все страницы)\n"
    "💸 <b>min_price</b> — Мин. цена (>= 0)\n"
    "💰 <b>max_price</b> — Макс. цена\n"
    "⭐ <b>min_rating</b> — Мин. рейтинг\n"
    "💬 <b>min_reviews</b> — Мин. кол-во отзывов\n"
    "🏷️ <b>brand</b> — Фильтр по бренду\n"
    "🧵 <b>threads</b> — Количество потоков для парсинга\n"
    "📝 <b>out_json</b> — Файл для JSON (вывод)\n"
    "📊 <b>out_csv</b> — Файл для CSV (вывод)\n"
    "⚙️ <b>pages</b> — Сколько страниц парсить\n"
    "\n<b>Пример:</b> /set min_price 1000\n<b>Пример:</b> /set brand Loreal"
)

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
router = Router()

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

COMMANDS = [
    ("/show", "📋 Показать текущие параметры"),
    ("/filters_only", "🎛️ Показать только фильтры"),
    ("/set", "✏️ Изменить параметр"),
    ("/toggle", "🔄 Переключить параметр (on/off)"),
    ("/filters", "🛠️ Изменить фильтры через кнопки"),
    ("/filters_wizard", "🧙‍♂️ Пошаговая настройка фильтров"),
    ("/start_parsing", "🚀 Запустить парсер"),
    ("/stop", "⛔ Остановить парсер"),
    ("/reset", "🧹 Сбросить параметры"),
    ("/status", "📊 Статус парсера"),
    ("/help", "ℹ️ Помощь и справка")
]

async def set_bot_commands(bot: Bot):
    await bot.set_my_commands([
        BotCommand(command=cmd, description=desc) for cmd, desc in COMMANDS
    ])

# --- Инлайн-клавиатуры для фильтров ---
filters_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💸 Мин. цена", callback_data="filter_min_price")],
        [InlineKeyboardButton(text="💰 Макс. цена", callback_data="filter_max_price")],
        [InlineKeyboardButton(text="⭐ Мин. рейтинг", callback_data="filter_min_rating")],
        [InlineKeyboardButton(text="💬 Мин. отзывы", callback_data="filter_min_reviews")],
        [InlineKeyboardButton(text="🏷️ Бренд", callback_data="filter_brand")],
    ]
)

# --- Инлайн-клавиатура для подтверждения сброса ---
reset_confirm_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, сбросить", callback_data="reset_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="reset_cancel")],
    ]
)

# --- Основная reply-клавиатура только для частых действий ---
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Показать параметры"), KeyboardButton(text="🛠️ Фильтры")],
        [KeyboardButton(text="🚀 Запустить парсер"), KeyboardButton(text="⛔ Остановить парсер")],
        [KeyboardButton(text="ℹ️ Помощь"), KeyboardButton(text="⬅️ В меню")],
    ],
    resize_keyboard=True
)

# --- Инлайн-клавиатура быстрых действий ---
inline_commands = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📋 Показать параметры", callback_data="show"),
         InlineKeyboardButton(text="🎛️ Только фильтры", callback_data="filters_only")],
        [InlineKeyboardButton(text="🛠️ Фильтры", callback_data="filters")],
        [InlineKeyboardButton(text="🚀 Запустить парсер", callback_data="start_parsing"),
         InlineKeyboardButton(text="⛔ Остановить парсер", callback_data="stop")],
        [InlineKeyboardButton(text="🧹 Сбросить параметры", callback_data="reset"),
         InlineKeyboardButton(text="📊 Статус", callback_data="status")],
        [InlineKeyboardButton(text="🧙‍♂️ Пошаговая настройка фильтров", callback_data="filters_wizard")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ]
)

# --- Клавиатура возврата в меню ---
back_to_menu_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ В меню", callback_data="back_to_menu")],
    ]
)

@router.message(Command('start'))
async def cmd_start(message: types.Message):
    text = (
        "Привет! Я бот для управления WB-парсером.\n"
        "<b>Доступные команды:</b>\n"
        + "\n".join([f"<b>{cmd}</b> — {desc}" for cmd, desc in COMMANDS]) +
        "\n\nИспользуй кнопки ниже или меню команд.\n\n" + PARAMS_HELP
    )
    await message.answer(text, parse_mode='HTML', reply_markup=main_keyboard)
    await message.answer("Быстрые действия:", reply_markup=inline_commands)

@router.message(lambda m: m.text and (m.text.startswith("/show") or "Показать параметры" in m.text))
async def cmd_show(message: types.Message):
    cfg = load_user_config()
    param_lines = [f"<b>{k}</b>: {v}" for k, v in cfg.items() if k != 'await_param']
    text = "<b>Текущие параметры:</b>"
    if param_lines:
        text += "\n" + "\n".join(param_lines)
    else:
        text += "\nНет сохранённых параметров."
    text += "\n\n<b>Доступные команды:</b>\n" + "\n".join([f"<b>{cmd}</b> — {desc}" for cmd, desc in COMMANDS])
    text += "\n\n" + PARAMS_HELP
    await message.answer(text, parse_mode='HTML', reply_markup=main_keyboard)
    await message.answer("Быстрые действия:", reply_markup=inline_commands)

@router.message(Command('set'))
async def cmd_set(message: types.Message):
    cfg = load_user_config()
    try:
        _, key, value = message.text.split(maxsplit=2)
        if key == "min_price":
            try:
                val = float(value)
                if val < 0:
                    await message.answer("❗ Мин. цена не может быть меньше 0!")
                    return
            except Exception:
                await message.answer("❗ Некорректное значение для min_price!")
                return
        set_param(cfg, key, value)
        await message.answer(f"Параметр <b>{key}</b> установлен в <b>{value}</b>", parse_mode='HTML')
    except Exception:
        await message.answer("Используй: /set ключ значение\nНапример: /set min_price 100")

@router.message(Command('toggle'))
async def cmd_toggle(message: types.Message):
    cfg = load_user_config()
    try:
        _, key = message.text.split(maxsplit=1)
        val = not bool(cfg.get(key, False))
        set_param(cfg, key, val)
        await message.answer(f"Параметр <b>{key}</b> переключён на <b>{val}</b>", parse_mode='HTML')
    except Exception:
        await message.answer("Используй: /toggle ключ\nНапример: /toggle enable_proxy")

@router.message(Command('filters'))
async def cmd_filters(message: types.Message):
    await message.answer("Выберите фильтр для изменения:", reply_markup=filters_keyboard)

@router.callback_query(lambda c: c.data.startswith("filter_"))
async def filter_callback(callback: CallbackQuery, state: FSMContext):
    filter_type = callback.data.replace("filter_", "")
    await callback.message.answer(f"Введите новое значение для фильтра: {filter_type}")
    await callback.answer()
    # Здесь можно добавить FSM для ожидания значения

@router.message()
async def set_value(msg: types.Message):
    cfg = load_user_config()
    param = cfg.get('await_param')
    if param:
        set_param(cfg, param, msg.text)
        cfg.pop('await_param', None)
        save_user_config(cfg)
        await msg.answer(f"Параметр <b>{param}</b> установлен в <b>{msg.text}</b>", parse_mode='HTML')

@router.message(Command('start_parsing'))
async def cmd_start_parsing(message: types.Message):
    if is_parser_running():
        await message.answer("Парсер уже запущен! Дождитесь завершения или используйте /stop для отмены.")
        return
    cfg = load_user_config()
    await message.answer("Парсер запущен! Ожидайте отчёт...")
    args = []
    for k, v in cfg.items():
        if isinstance(v, bool):
            if v:
                args.append(f"--{k}")
        elif k != 'await_param':
            args.append(f"--{k}")
            args.append(str(v))
    progress_task = asyncio.create_task(send_progress_updates(message.chat.id))
    proc = await asyncio.create_subprocess_exec(
        'python', 'main.py', *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    save_parser_pid(proc.pid)
    stdout, stderr = await proc.communicate()
    clear_parser_pid()
    progress_task.cancel()
    await send_file_if_exists(message.chat.id, cfg.get('out_json', 'results.json'), caption="Результаты WB парсера (JSON)")
    await send_file_if_exists(message.chat.id, cfg.get('out_csv', 'results.csv'), caption="Результаты WB парсера (CSV)")
    await send_file_if_exists(message.chat.id, cfg.get('error_log', 'errors.log'), caption="Лог ошибок WB парсера")
    await message.answer("Парсинг завершён! Итоги и файлы отправлены.")

@router.message(Command('stop'))
async def cmd_stop(message: types.Message):
    if not is_parser_running():
        await message.answer("Парсер не запущен.")
        return
    try:
        with open(PARSER_PROCESS_FILE, 'r') as f:
            pid = int(f.read().strip())
        os.kill(pid, 9)
        clear_parser_pid()
        await message.answer("Парсер остановлен.")
    except Exception as e:
        await message.answer(f"Ошибка при остановке парсера: {e}")

@router.message(Command('help'))
@router.message(lambda m: m.text and ("Помощь" in m.text))
async def cmd_help(message: types.Message):
    text = (
        "<b>ℹ️ Помощь и справка</b>\n"
        "Этот бот позволяет управлять парсером Wildberries через Telegram.\n\n"
        + PARAMS_HELP +
        "\n\n<b>Основные команды:</b>\n"
        + "\n".join([f"<b>{cmd}</b> — {desc}" for cmd, desc in COMMANDS])
    )
    await message.answer(text, parse_mode='HTML', reply_markup=main_keyboard)
    await message.answer("Быстрые действия:", reply_markup=inline_commands)

@router.message(Command('reset'))
async def cmd_reset(message: types.Message):
    await message.answer("Вы уверены, что хотите сбросить все параметры?", reply_markup=reset_confirm_keyboard)

@router.callback_query(lambda c: c.data == "reset_confirm")
async def reset_confirm(callback: CallbackQuery, state: FSMContext):
    # Сбросить параметры пользователя
    reset_user_config(callback.from_user.id)
    await callback.message.answer("Все параметры сброшены! 🧹")
    await callback.answer()

@router.callback_query(lambda c: c.data == "reset_cancel")
async def reset_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Сброс отменён.")
    await callback.answer()

@router.message(lambda m: m.text and (m.text.startswith("/filters_only") or "Только фильтры" in m.text))
async def cmd_filters_only(message: types.Message):
    cfg = load_user_config()
    filter_keys = [
        ("min_price", "💸 Мин. цена"),
        ("max_price", "💰 Макс. цена"),
        ("min_rating", "⭐ Мин. рейтинг"),
        ("min_reviews", "💬 Мин. отзывы"),
        ("brand", "🏷️ Бренд"),
    ]
    lines = [f"{emoji} <b>{key}</b>: {cfg.get(key, 'не задано')}" for key, emoji in filter_keys]
    text = "<b>Текущие фильтры:</b>\n" + "\n".join(lines)
    await message.answer(text, parse_mode='HTML', reply_markup=main_keyboard)
    await message.answer("Быстрые действия:", reply_markup=inline_commands)

@router.message(lambda m: m.text and (m.text.startswith("/status") or "Статус" in m.text))
async def cmd_status(message: types.Message):
    running = is_parser_running()
    status = "🟢 Парсер запущен" if running else "🔴 Парсер не запущен"
    # Можно добавить больше информации, если есть прогресс-файл
    progress = ""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding='utf-8') as f:
            try:
                prog = json.load(f)
                progress = (
                    f"\nПакет: <b>{prog.get('batch_num', '?')}/{prog.get('total_batches', '?')}</b>"
                    f"\nОбработано ссылок: <b>{prog.get('total', '?')}</b>"
                    f"\nНайдено подходящих: <b>{prog.get('found', '?')}</b>"
                    f"\nВремя работы: <b>{prog.get('work_time', 0):.1f} мин</b>"
                )
            except Exception:
                progress = "\nНет данных о прогрессе."
    await message.answer(f"<b>📊 Статус парсера</b>\n{status}{progress}", parse_mode='HTML', reply_markup=main_keyboard)
    await message.answer("Быстрые действия:", reply_markup=inline_commands)

@router.callback_query(lambda c: c.data in ["show", "filters_only", "filters", "start_parsing", "stop", "reset", "status", "help"])
async def quick_command_callback(callback: types.CallbackQuery, bot: Bot):
    if callback.data == "show":
        await cmd_show(callback.message)
    elif callback.data == "filters_only":
        await cmd_filters_only(callback.message)
    elif callback.data == "filters":
        await cmd_filters(callback.message)
    elif callback.data == "start_parsing":
        await cmd_start_parsing(callback.message)
    elif callback.data == "stop":
        await cmd_stop(callback.message)
    elif callback.data == "reset":
        await cmd_reset(callback.message)
    elif callback.data == "status":
        await cmd_status(callback.message)
    elif callback.data == "help":
        await cmd_help(callback.message)
    await callback.answer()

class FilterWizard(StatesGroup):
    min_price = State()
    max_price = State()
    min_rating = State()
    min_reviews = State()
    brand = State()
    confirm = State()

@router.message(lambda m: m.text and (m.text.startswith("/filters_wizard") or "Пошаговая настройка фильтров" in m.text))
async def start_filters_wizard(message: types.Message, state: FSMContext):
    await message.answer("🧙‍♂️ Пошаговая настройка фильтров.\nВведите минимальную цену (min_price):", reply_markup=main_keyboard)
    await state.set_state(FilterWizard.min_price)

@router.callback_query(lambda c: c.data == "filters_wizard")
async def start_filters_wizard_cb(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("🧙‍♂️ Пошаговая настройка фильтров.\nВведите минимальную цену (min_price):", reply_markup=main_keyboard)
    await state.set_state(FilterWizard.min_price)
    await callback.answer()

@router.message(FilterWizard.min_price)
async def wizard_min_price(message: types.Message, state: FSMContext):
    try:
        val = float(message.text)
        if val < 0:
            await message.answer("❗ Мин. цена не может быть меньше 0! Введите ещё раз:")
            return
        await state.update_data(min_price=val)
        await message.answer("Введите максимальную цену (max_price):")
        await state.set_state(FilterWizard.max_price)
    except Exception:
        await message.answer("❗ Введите число для min_price:")

@router.message(FilterWizard.max_price)
async def wizard_max_price(message: types.Message, state: FSMContext):
    try:
        val = float(message.text)
        await state.update_data(max_price=val)
        await message.answer("Введите минимальный рейтинг (min_rating):")
        await state.set_state(FilterWizard.min_rating)
    except Exception:
        await message.answer("❗ Введите число для max_price:")

@router.message(FilterWizard.min_rating)
async def wizard_min_rating(message: types.Message, state: FSMContext):
    try:
        val = float(message.text)
        await state.update_data(min_rating=val)
        await message.answer("Введите минимальное количество отзывов (min_reviews):")
        await state.set_state(FilterWizard.min_reviews)
    except Exception:
        await message.answer("❗ Введите число для min_rating:")

@router.message(FilterWizard.min_reviews)
async def wizard_min_reviews(message: types.Message, state: FSMContext):
    try:
        val = int(message.text)
        await state.update_data(min_reviews=val)
        await message.answer("Введите бренд (brand) или оставьте пустым:")
        await state.set_state(FilterWizard.brand)
    except Exception:
        await message.answer("❗ Введите целое число для min_reviews:")

@router.message(FilterWizard.brand)
async def wizard_brand(message: types.Message, state: FSMContext):
    await state.update_data(brand=message.text.strip() if message.text.strip() else None)
    data = await state.get_data()
    text = (
        "<b>Вы ввели фильтры:</b>\n"
        f"💸 min_price: <b>{data.get('min_price')}</b>\n"
        f"💰 max_price: <b>{data.get('max_price')}</b>\n"
        f"⭐ min_rating: <b>{data.get('min_rating')}</b>\n"
        f"💬 min_reviews: <b>{data.get('min_reviews')}</b>\n"
        f"🏷️ brand: <b>{data.get('brand') or 'не задано'}</b>\n\n"
        "Сохранить эти значения?"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сохранить", callback_data="wizard_save")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="wizard_cancel")],
    ])
    await message.answer(text, parse_mode='HTML', reply_markup=kb)
    await state.set_state(FilterWizard.confirm)

@router.callback_query(lambda c: c.data == "wizard_save", FilterWizard.confirm)
async def wizard_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cfg = load_user_config()
    cfg.update({
        "min_price": data.get("min_price"),
        "max_price": data.get("max_price"),
        "min_rating": data.get("min_rating"),
        "min_reviews": data.get("min_reviews"),
        "brand": data.get("brand"),
    })
    save_user_config(cfg)
    await callback.message.answer("✅ Фильтры сохранены!", reply_markup=main_keyboard)
    await state.clear()
    await callback.answer()

@router.callback_query(lambda c: c.data == "wizard_cancel", FilterWizard.confirm)
async def wizard_cancel(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("❌ Пошаговая настройка отменена.", reply_markup=main_keyboard)
    await state.clear()
    await callback.answer()

# --- Обработка возврата в меню ---
@router.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    await callback.message.answer("Главное меню:", reply_markup=main_keyboard)
    await callback.message.answer("Быстрые действия:", reply_markup=inline_commands)
    await callback.answer()

# --- Обработка команды /help и кнопки ---
@router.callback_query(lambda c: c.data == "help")
async def help_callback(callback: CallbackQuery):
    text = (
        "<b>ℹ️ Помощь и справка</b>\n"
        "Этот бот позволяет управлять парсером Wildberries через Telegram.\n\n"
        + PARAMS_HELP +
        "\n\n<b>Основные команды:</b>\n"
        + "\n".join([f"<b>{cmd}</b> — {desc}" for cmd, desc in COMMANDS])
    )
    await callback.message.answer(text, parse_mode='HTML', reply_markup=main_keyboard)
    await callback.message.answer("Быстрые действия:", reply_markup=inline_commands)
    await callback.answer()

# --- Обработка возврата в меню по тексту ---
@router.message(lambda m: m.text and ("В меню" in m.text))
async def back_to_menu_text(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_keyboard)
    await message.answer("Быстрые действия:", reply_markup=inline_commands)

if __name__ == '__main__':
    import asyncio
    async def main():
        dp = Dispatcher()
        dp.include_router(router)
        await set_bot_commands(bot)
        await dp.start_polling(bot)
    asyncio.run(main()) 