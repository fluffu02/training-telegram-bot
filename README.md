# Training Telegram Bot
Telegram-бот для ежедневных напоминаний о тренировках, еженедельного чек-ина по весу и сохранения прогресса.
## Функции
- Отправляет ежедневную тренировку по расписанию.
- Показывает тренировку на сегодня и программу на неделю.
- Даёт кнопки для отметки тренировки как выполненной или пропущенной.
- Принимает и сохраняет вес пользователя.
- Сохраняет Telegram `file_id` фото формы за неделю.
- Показывает историю веса и фото через команду `/progress`.
- Ведёт SQLite-базу пользователей, сообщений и статусов.
- Поддерживает административную статистику для `ADMIN_USER_ID`.
## Требования
- Python 3.12 или совместимая версия Python 3.11+.
- Telegram-бот, созданный через `@BotFather`.
- Заполненный файл `.env`.
## Установка
Склонируйте репозиторий и перейдите в папку проекта:
```powershell
git clone <repo_url>
cd training-telegram-bot
```
Создайте и активируйте виртуальное окружение:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
Установите зависимости:
```powershell
pip install -r requirements.txt
```
## Настройка `.env`
Создайте `.env` из примера:
```powershell
Copy-Item .env.example .env
```
Заполните минимум эти переменные:
- `BOT_TOKEN` — токен Telegram-бота от `@BotFather`.
- `ADMIN_USER_ID` — Telegram ID администратора для админ-команд, можно оставить пустым.
- `OPENAI_API_KEY` — ключ OpenAI, если будет использоваться ИИ-функциональность; текущая логика бота может работать без него.
Остальные переменные можно оставить как в `.env.example`:
- `TIMEZONE` — часовой пояс расписания.
- `DAILY_REMINDER_TIME` — время ежедневной тренировки.
- `WEEKLY_REMINDER_DAY` и `WEEKLY_REMINDER_TIME` — день и время еженедельного чек-ина.
- `AFTERNOON_REMINDER_TIME` — дневное напоминание.
- `SLEEP_REMINDER_TIME` — вечернее напоминание.
- `CLEAR_TIME` и `CLEAR_LIMIT` — настройки очистки известных боту сообщений.
- `PROGRAM_START_DATE` — дата старта программы для прогрессии.
- `DATABASE_PATH` — локальный путь к SQLite-базе.
- `PROGRAM_PATH` — путь к JSON-файлу программы тренировок.
## Запуск
```powershell
python -m app.main
```
После запуска напишите боту `/start`.
## Запуск в Docker
1. Создайте `.env` из примера:
```bash
cp .env.example .env
```
2. Заполните минимум `BOT_TOKEN` и при необходимости `ADMIN_USER_ID`.
3. Соберите контейнер:
```bash
docker compose build
```
4. Запустите бота:
```bash
docker compose up -d
```
5. Посмотрите логи:
```bash
docker compose logs -f bot
```
6. Остановите контейнер:
```bash
docker compose down
```
SQLite-база хранится в Docker volume `bot_data` и не теряется при пересборке контейнера.
Если нужна своя программа тренировок, замените `program.example.json` на свой файл или поменяйте `PROGRAM_PATH` в `.env`.
## Команды бота
- `/start` — подключить чат к напоминаниям.
- `/today` — показать тренировку на сегодня.
- `/week` — показать программу на неделю.
- `/weight` — записать или посмотреть вес.
- `/progress` — посмотреть историю веса и фото.
- `/clear` — очистить известные боту сообщения.
- `/help` — показать список команд.
Фото без команды сохраняется как фото формы за текущую неделю.
## Данные и безопасность
- `.env` не должен попадать в GitHub.
- `.venv/`, `data/`, `photos/`, локальные базы SQLite и `__pycache__` исключены через `.gitignore`.
- Локальная база по умолчанию создаётся в `data/bot.sqlite3`.
- В Docker база хранится по пути `/app/data/bot.sqlite3` внутри контейнера и мапится в volume `bot_data`.
- Для переносимого запуска пример программы тренировок хранится в `program.example.json`, а `.env.example` указывает `PROGRAM_PATH=program.example.json`.
- Если на сервере нужна другая программа, создайте свой JSON-файл и укажите путь в `PROGRAM_PATH`.
## Перенос на другой сервер
Минимальный порядок запуска на новом сервере:
```bash
git clone <repo_url>
cd training-telegram-bot
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
python -m app.main
```
В `.env` обязательно укажите реальный `BOT_TOKEN`. Локальные данные и база будут созданы на сервере автоматически.
## Публикация на GitHub
После создания репозитория на GitHub выполните:
```bash
git remote add origin <repo_url>
git branch -M main
git push -u origin main
```
