import telebot
import json
import schedule
import time
import threading
from datetime import datetime
import os

# Токен бота
TOKEN = 'YOUR_BOT_TOKEN'
bot = telebot.TeleBot(TOKEN)

# ID канала (с @ или без)
CHANNEL_ID = '@your_channel_username'  # или '-1001234567890' для приватных каналов

# Пример JSON данных (в реальном проекте эти данные будут загружаться из файлов или БД)
sample_data = {
    "краткая_аналитика": "Металлург Магнитогорск является явным фаворитом, учитывая текущую форму, турнирное положение и историю личных встреч.",
    "прогноз_ставки": "П2 в основное время",
    "обоснование": "Металлург демонстрирует впечатляющую игру с девятью победами в последних одиннадцати матчах и мощным атакующим потенциалом, тогда как Шанхай Драгонс находится в кризисе, не зная побед в основное время уже семь матчей подряд.",
    "рекомендуемый_коэффициент": "1.80",
    "уровень_уверенности": "9/10",
    "риски": "Основной риск заключается в возможной нестабильности Металлурга в основное время, так как в последних трёх играх они не могли одержать победу в основное время.",
    "альтернативные_ставки": [
        "П2 с форой (-1)",
        "Тотал больше 5.5"
    ],
    "мотивация": "Сделайте ставку на победу Металлурга и увеличьте свой выигрыш с привлекательным коэффициентом!"
}

# Функция для загрузки данных (в реальном проекте будет загрузка из файлов) ДОБАВИТЬ ИИ
def load_data(data_source):
    """Загружает данные для поста"""
    return data_source

# Шаблоны постов
def create_post_template(data, post_number):
    """Создает текст поста на основе данных и номера поста"""
    
    templates = {
        1: "🎯 *ПРОГНОЗ НА ДЕНЬ* 🎯\n\n",
        2: "📊 *ДЕТАЛЬНЫЙ АНАЛИЗ* 📊\n\n",
        3: "⚡ *ГОРЯЧИЙ ПРОГНОЗ* ⚡\n\n",
        4: "🔮 *ВЕЧЕРНИЙ ПРОГНОЗ* 🔮\n\n",
        5: "💎 *ПРЕМИУМ ПРОГНОЗ* 💎\n\n",
        6: "🌙 *НОЧНОЙ ЭКСПРЕСС* 🌙\n\n"
    }
    
    post = templates.get(post_number, "📈 *ПРОГНОЗ ОТ ЭКСПЕРТА* 📈\n\n")
    
    post += f"*Прогноз ставки:* {data['прогноз_ставки']}\n"
    post += f"*Коэффициент:* {data['рекомендуемый_коэффициент']}\n"
    post += f"*Уверенность:* {data['уровень_уверенности']}\n\n"
    
    post += "*Краткая аналитика:*\n"
    post += f"{data['краткая_аналитика']}\n\n"
    
    post += "*Обоснование прогноза:*\n"
    post += f"{data['обоснование']}\n\n"
    
    post += "*Возможные риски:*\n"
    post += f"{data['риски']}\n\n"
    
    if data['альтернативные_ставки']:
        post += "*Альтернативные ставки:*\n"
        for i, alt in enumerate(data['альтернативные_ставки'], 1):
            post += f"{i}. {alt}\n"
        post += "\n"
    
    post += f"💪 *{data['мотивация']}*\n\n"
    
    post += "————————————\n"
    post += "⚠️ *Важно:* Ставки на спорт связаны с риском. Ставьте только ту сумму, которую готовы потерять.\n"
    post += f"📅 *Время публикации:* {datetime.now().strftime('%H:%M %d.%m.%Y')}\n"
    post += "#прогноз #ставки #аналитика"
    
    return post

# Функции для каждого поста
def send_post_12_00():
    """Отправка поста в 12:00"""
    data = load_data("post1")  # Можно заменить на загрузку конкретных данных
    post_text = create_post_template(data, 1)
    
    try:
        # Отправка поста с картинкой
        with open('images/post1.jpg', 'rb') as photo:
            bot.send_photo(
                CHANNEL_ID, 
                photo, 
                caption=post_text, 
                parse_mode='Markdown'
            )
        print(f"[{datetime.now()}] Пост 1 (12:00) отправлен в канал")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки поста 1: {e}")

def send_post_14_00():
    """Отправка поста в 14:00"""
    data = load_data("post2")
    post_text = create_post_template(data, 2)
    
    try:
        with open('images/post2.jpg', 'rb') as photo:
            bot.send_photo(
                CHANNEL_ID, 
                photo, 
                caption=post_text, 
                parse_mode='Markdown'
            )
        print(f"[{datetime.now()}] Пост 2 (14:00) отправлен в канал")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки поста 2: {e}")

def send_post_16_00():
    """Отправка поста в 16:00"""
    data = load_data("post3")
    post_text = create_post_template(data, 3)
    
    try:
        with open('images/post3.jpg', 'rb') as photo:
            bot.send_photo(
                CHANNEL_ID, 
                photo, 
                caption=post_text, 
                parse_mode='Markdown'
            )
        print(f"[{datetime.now()}] Пост 3 (16:00) отправлен в канал")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки поста 3: {e}")

def send_post_18_00():
    """Отправка поста в 18:00"""
    data = load_data("post4")
    post_text = create_post_template(data, 4)
    
    try:
        with open('images/post4.jpg', 'rb') as photo:
            bot.send_photo(
                CHANNEL_ID, 
                photo, 
                caption=post_text, 
                parse_mode='Markdown'
            )
        print(f"[{datetime.now()}] Пост 4 (18:00) отправлен в канал")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки поста 4: {e}")

def send_post_20_00():
    """Отправка поста в 20:00"""
    data = load_data("post5")
    post_text = create_post_template(data, 5)
    
    try:
        with open('images/post5.jpg', 'rb') as photo:
            bot.send_photo(
                CHANNEL_ID, 
                photo, 
                caption=post_text, 
                parse_mode='Markdown'
            )
        print(f"[{datetime.now()}] Пост 5 (20:00) отправлен в канал")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки поста 5: {e}")

def send_post_22_00():
    """Отправка поста в 22:00"""
    data = load_data("post6")
    post_text = create_post_template(data, 6)
    
    try:
        with open('images/post6.jpg', 'rb') as photo:
            bot.send_photo(
                CHANNEL_ID, 
                photo, 
                caption=post_text, 
                parse_mode='Markdown'
            )
        print(f"[{datetime.now()}] Пост 6 (22:00) отправлен в канал")
    except Exception as e:
        print(f"[{datetime.now()}] Ошибка отправки поста 6: {e}")

# Настройка расписания
def setup_schedule():
    """Настраивает расписание отправки постов"""
    schedule.every().day.at("12:00").do(send_post_12_00)
    schedule.every().day.at("14:00").do(send_post_14_00)
    schedule.every().day.at("16:00").do(send_post_16_00)
    schedule.every().day.at("18:00").do(send_post_18_00)
    schedule.every().day.at("20:00").do(send_post_20_00)
    schedule.every().day.at("22:00").do(send_post_22_00)
    
    print("Расписание настроено:")
    print("12:00 - Пост 1")
    print("14:00 - Пост 2")
    print("16:00 - Пост 3")
    print("18:00 - Пост 4")
    print("20:00 - Пост 5")
    print("22:00 - Пост 6")

# Функция для запуска планировщика в отдельном потоке
def run_scheduler():
    """Запускает планировщик в отдельном потоке"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Проверка каждую минуту

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    
    # Настройка расписания
    setup_schedule()
    
    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Запуск поллинга бота (для обработки команд, если нужно)
    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"Ошибка в работе бота: {e}")