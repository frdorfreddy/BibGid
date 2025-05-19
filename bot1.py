# === Импортируем необходимые библиотеки === 
import asyncio  # Для запуска асинхронного кода
import logging  # Для логирования ошибок
import requests  # Для выполнения HTTP-запросов к сайту библиотеки
from bs4 import BeautifulSoup  # Для парсинга HTML-страниц

# === Импортируем компоненты из aiogram (Telegram-бот) ===
from aiogram import Bot, Dispatcher, F  # Основные классы и фильтры
from aiogram.filters import Command  # Для фильтрации по командам (например, /start)
from aiogram.types import Message  # Тип для получаемых сообщений
from aiogram.fsm.storage.memory import MemoryStorage  # Хранение состояния FSM в памяти
from aiogram.fsm.state import State, StatesGroup  # Классы для описания FSM-состояний
from aiogram.fsm.context import FSMContext  # Контекст FSM (состояния пользователя) 
from conf1 import TOKEN, DEEPSEEK_TOKEN  # Импорт токена и ключа

from generate1 import ai_generate  # Функция генерации ответа от DeepSeek

# === Константы и сессия ===
BASE_URL = "https://e-library.syktsu.ru"  # Базовый адрес библиотеки
LOGIN_URL = f"{BASE_URL}/megapro/Web/Home/RegRdr"  # URL для авторизации
SEARCH_URL = f"{BASE_URL}/megapro/Web/SearchResult/Simple"  # URL для запроса поиска

SERVICE_USER_ID = "21250506"  # ID служебного пользователя
SERVICE_USER_NAME = "bot"  # Имя служебного пользователя

# === Глобальная HTTP-сессия (requests) ===
session = requests.Session()  # Создаём сессию для повторного использования соединения
session.verify = False  # Отключаем проверку SSL-сертификатов (небезопасно в проде)
session.headers.update({  # Устанавливаем заголовки по умолчанию
    "User-Agent": "Mozilla/5.0",  # Чтобы нас не блокировали как бота
    "X-Requested-With": "XMLHttpRequest",  # Заголовок для имитации AJAX
    "Content-Type": "application/x-www-form-urlencoded"  # Тип отправки формы
})

# === Класс состояний FSM (Finite State Machine) ===
class SearchForm(StatesGroup):
    keywords = State()  # Одно состояние — ожидание ключевых слов от пользователя

# === Создание экземпляров бота и диспетчера ===
bot = Bot(token=TOKEN)  # Создаём бота с переданным токеном
dp = Dispatcher(storage=MemoryStorage())  # Создаём диспетчер и подключаем хранилище состояний

# === Авторизация служебного пользователя при запуске ===
def authorize_service_user():
    try:
        session.get(f"{BASE_URL}/megapro/Web", timeout=10)  # Получаем куки

        payload = {
            "id": SERVICE_USER_ID,  # Передаём ID
            "name": SERVICE_USER_NAME  # Передаём имя
        }

        # Отправляем POST-запрос на авторизацию
        response = session.post(LOGIN_URL, data=payload, timeout=10)
        if "ok" not in response.text.lower():
            raise Exception("Авторизация не удалась")

        print("Авторизация успешна")
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
        raise  # Прерываем выполнение при ошибке

# === Обработка команды /start ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Введите команду /info для получения информации об использовании бота или /search для поиска книг по ключевым словам.")


# === Обработка команды /info (информация о боте) ===
@dp.message(Command("info"))
async def cmd_info(message: Message):
    info_text = (
        "<b>Инструкция по использованию бота:</b>\n\n"
        "1) Введите /search — чтобы начать поиск книг в электронной библиотеке.\n"
        "2) После этого введите ключевые слова (например, история России).\n"
        "Бот найдёт книги по вашему запросу и отправит ссылки на них.\n\n"
        "Также вы можете задать вопрос, например:\n"
        "«Мне нравятся книги о фантастике, что можешь посоветовать?»\n"
        "Или использовать одну из этих фраз: мне нравится, посоветуй, что можешь, порекомендуй, что почитать, хочу что-то интересное,\n"
        "какую книгу, интересное о, подскажи книгу, предложи — и бот предложит интересные книги с помощью искусственного интеллекта (DeepSeek).\n\n"
        "Важно: бот не выдаёт ссылки на скачивание, если книга недоступна в электронном виде.\n"
        "Если доступен PDF — будет кнопка «Скачать» и ссылка на онлайн-версию."
    )
    await message.answer(info_text, parse_mode="HTML", disable_web_page_preview=True)


# === Обработка команды /search (переход к состоянию ввода ключевых слов) ===
@dp.message(F.text == "/search")
async def cmd_search(message: Message, state: FSMContext):
    await state.set_state(SearchForm.keywords)  # Устанавливаем состояние FSM
    await message.answer("Введите ключевые слова для поиска:")

# === Обработка ввода ключевых слов и выполнение поиска или рекомендации ===
@dp.message(SearchForm.keywords)
async def process_keywords(message: Message, state: FSMContext):
    keywords = message.text.strip()
    if not keywords:
        await message.answer("Введите хотя бы одно ключевое слово.")
        return

    try:
        msg = await message.answer("Обрабатываю запрос...")

        # === Проверка: это рекомендация или библиотечный поиск? ===
        lowered = keywords.lower()
        if any(phrase in lowered for phrase in [
            "мне нравится", "посоветуй", "что можешь", "порекомендуй", "что почитать",
            "хочу что-то интересное", "какую книгу", "интересное о", "подскажи книгу",
            "предложи"
        ]):
            await bot.delete_message(message.chat.id, msg.message_id)
            response = await ai_generate(keywords)
            await message.answer(response, parse_mode="Markdown")
        else:
            # === Обычный поиск в библиотеке ===
            results = await asyncio.to_thread(search_books, keywords)
            await bot.delete_message(message.chat.id, msg.message_id)

            if results:
                for item in results:
                    await message.answer(item, parse_mode="HTML", disable_web_page_preview=True)
            else:
                await message.answer("Книги не найдены.")

    except Exception as e:
        await message.answer(f"Ошибка: {e}")
    finally:
        await state.clear()  # Сброс состояния FSM

# === Функция поиска книг через requests ===
def search_books(keywords: str) -> list[str]:
    payload = {
        "simpleCond": keywords,  # Ключевые слова
        "cond_words": "all",  # Искомые слова: все
        "cond_match": "exect_match",  # Точное совпадение
        "filter_dateFrom": "",  # Фильтрация по дате — не используется
        "filter_dateTo": "",
        "sort": "SORT1"  # Сортировка по умолчанию
    }

    try:
        response = session.post(SEARCH_URL, data=payload, timeout=15)  # Отправляем POST-запрос на поиск
        if response.status_code != 200:
            raise Exception(f"Ошибка запроса: {response.status_code}")

        html = response.text

        # Сохраняем HTML для отладки
        with open("debug.html", "w", encoding="utf-8") as f:
            f.write(html)

        soup = BeautifulSoup(html, "html.parser")  # Парсим HTML с помощью BeautifulSoup
        results = []

        # Ищем строки таблицы с книгами
        book_rows = soup.find_all("tr", class_=["docOdd", "docEven"])
        for row in book_rows:
            book_table = row.find("table", class_="docTable")  # Находим вложенную таблицу с данными
            if not book_table:
                continue

            cells = book_table.find_all("tr")  # Строки внутри таблицы книги
            title_text = ""
            link = None

            for tr in cells:
                tds = tr.find_all("td")  # Колонки в строке
                if len(tds) < 2:
                    continue

                label = tds[0].get_text(strip=True)  # Название поля
                content = tds[1].get_text(strip=True)  # Значение поля

                if label.startswith("Книга"):
                    title_text = f"<b>{content}</b>"
                elif label.startswith("Шифры"):
                    title_text += f"\nШифры: {content}"
                elif label.startswith("Ключевые слова"):
                    title_text += f"\nКлючевые слова: {content}"
                elif label.startswith("Аннотация"):
                    title_text += f"\nАннотация: {content[:300]}..."

                if label.startswith("Электронная версия"):
                    link_tag = tds[1].find("a", class_="load_res")
                    if link_tag and link_tag.get("href"):
                        link = BASE_URL + link_tag["href"]

            if title_text:
                if link:
                    title_text += f"\n <a href='{link}'>Скачать PDF</a>"
                    title_text += f"\n <a href='{link}'>Перейти к книге</a>"
                results.append(title_text)  # Добавляем результат в список

        return results
    except Exception as e:
        logging.error(f"Ошибка поиска: {e}")
        return [f"Произошла ошибка при поиске: {e}"]

# === Точка входа в приложение ===
async def main():
    authorize_service_user()  # Авторизуемся как служебный пользователь
    await dp.start_polling(bot)  # Запускаем бота и начинаем опрашивать Telegram

# === Запуск приложения (если выполняется напрямую) ===
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)  # Настройка логирования
    try:
        asyncio.run(main())  # Запуск асинхронного main()
    except KeyboardInterrupt:
        print("Выход")  # Завершение по Ctrl+C
