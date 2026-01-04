import telebot
import json
import schedule
import time
import threading
from datetime import datetime, timedelta
import os
from database import SportsDatabase
from AI import SportPredictionAnalyzer
from typing import Optional, List, Dict, Tuple
import re

# Токен бота
TOKEN = '7580679285:AAHc6_XSg4G1hgyCpZ1kDb5z4njnj6ePY0c'
bot = telebot.TeleBot(TOKEN)

# ID канала (с @ или без)
CHANNEL_ID = '@test_forecast'  # или '-1001234567890' для приватных каналов

# ID администратора (замените на свой Telegram ID)
ADMIN_ID = 409000348  # Здесь должен быть ваш Telegram ID

# Состояния для FSM (Finite State Machine) ручной публикации
class ManualPostState:
    WAITING_POST_NUMBER = 1
    WAITING_MATCH_SELECTION = 2
    WAITING_CONFIRMATION = 3

# Хранилище состояний пользователей
user_states = {}
manual_post_data = {}


class TimeParser:
    """Класс для парсинга времени из текстовых строк"""
    
    @staticmethod
    def parse_time_string(time_str: str) -> Optional[datetime]:
        """
        Парсит строку времени и возвращает datetime объект
        
        Поддерживаемые форматы:
        - "Сегодня 21:00"
        - "Завтра 14:30"
        - "14:30" (сегодняшнее время)
        - "15.01.2024 20:00"
        """
        if not time_str:
            return None
            
        time_str = time_str.strip()
        now = datetime.now()
        
        try:
            # Формат: "Сегодня 21:00"
            if time_str.startswith("Сегодня"):
                time_part = time_str.replace("Сегодня", "").strip()
                hour, minute = map(int, time_part.split(":"))
                return datetime(now.year, now.month, now.day, hour, minute)
            
            # Формат: "Завтра 14:30"
            elif time_str.startswith("Завтра"):
                time_part = time_str.replace("Завтра", "").strip()
                hour, minute = map(int, time_part.split(":"))
                tomorrow = now + timedelta(days=1)
                return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute)
            
            # Формат: "Вчера 21:00" - пропускаем
            elif time_str.startswith("Вчера"):
                return None
            
            # Формат: "14:30" (просто время)
            elif re.match(r'^\d{1,2}:\d{2}$', time_str):
                hour, minute = map(int, time_str.split(":"))
                # Если указанное время уже прошло сегодня, считаем что это на завтра
                if hour < now.hour or (hour == now.hour and minute <= now.minute):
                    tomorrow = now + timedelta(days=1)
                    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute)
                else:
                    return datetime(now.year, now.month, now.day, hour, minute)
            
            # Формат: "15.01.2024 20:00"
            elif re.match(r'^\d{2}\.\d{2}\.\d{4} \d{1,2}:\d{2}$', time_str):
                date_part, time_part = time_str.split()
                day, month, year = map(int, date_part.split("."))
                hour, minute = map(int, time_part.split(":"))
                return datetime(year, month, day, hour, minute)
            
            return None
            
        except Exception as e:
            print(f"Ошибка парсинга времени '{time_str}': {e}")
            return None
    
    @staticmethod
    def is_future_match(time_str: str) -> bool:
        """
        Проверяет, является ли матч будущим (не прошедшим)
        
        Returns:
            bool: True если матч еще не начался, False если прошел или не удалось определить
        """
        match_time = TimeParser.parse_time_string(time_str)
        if not match_time:
            return False  # Не удалось определить время
        
        # Добавляем небольшой буфер (30 минут) на случай если матч только начался
        return match_time > datetime.now() - timedelta(minutes=30)


class TelegramBotWithDB:
    def __init__(self, db_path='sports_data.db'):
        self.db = SportsDatabase(db_path)
        self.analyzer = None
        self.scheduled_posts = {}  # Словарь для отслеживания запланированных постов
        
    def initialize_analyzer(self, api_key):
        """Инициализация анализатора с API ключом"""
        self.analyzer = SportPredictionAnalyzer(api_key=api_key, db_path='sports_data.db')
    
    def get_next_matches_sorted(self, limit: int = 10) -> List[Dict]:
        """
        Получение следующих матчей, отсортированных по времени начала
        
        Args:
            limit (int): Максимальное количество матчей для возврата
        
        Returns:
            List[Dict]: Список матчей, отсортированных по времени начала
        """
        # Получаем все неиспользованные матчи
        all_unused = self.db.get_unused_matches(limit=100)  # Берем больше для сортировки
        
        if not all_unused:
            return []
        
        # Фильтруем матчи
        filtered_matches = []
        
        for match in all_unused:
            start_time = match.get('start_time', '')
            
            # Проверяем, является ли матч будущим
            if TimeParser.is_future_match(start_time):
                # Парсим время для сортировки
                match_time = TimeParser.parse_time_string(start_time)
                if match_time:
                    match['parsed_time'] = match_time
                    filtered_matches.append(match)
        
        # Сортируем по времени начала
        filtered_matches.sort(key=lambda x: x.get('parsed_time', datetime.max))
        
        return filtered_matches[:limit]
    
    def get_all_available_matches(self, limit: int = 50) -> List[Dict]:
        """
        Получает все доступные матчи (неиспользованные и будущие)
        
        Args:
            limit (int): Максимальное количество матчей
        
        Returns:
            List[Dict]: Список доступных матчей
        """
        return self.get_next_matches_sorted(limit=limit)
    
    def get_match_by_index(self, index: int) -> Optional[Dict]:
        """
        Получает матч по индексу из списка доступных матчей
        
        Args:
            index (int): Индекс матча (начиная с 1)
        
        Returns:
            Optional[Dict]: Данные матча или None
        """
        matches = self.get_all_available_matches(limit=50)
        if 0 < index <= len(matches):
            return matches[index - 1]
        return None
    
    def get_match_for_time_slot(self, time_slot: str) -> Optional[Dict]:
        """
        Получает наиболее подходящий матч для временного слота
        
        Args:
            time_slot (str): Временной слот ('12:00', '14:00' и т.д.)
        
        Returns:
            Optional[Dict]: Данные матча или None
        """
        # Получаем отсортированные матчи
        sorted_matches = self.get_next_matches_sorted(limit=20)
        
        if not sorted_matches:
            return None
        
        # Преобразуем time_slot в datetime для сравнения
        try:
            slot_hour = int(time_slot.split(':')[0])
            now = datetime.now()
            slot_time = datetime(now.year, now.month, now.day, slot_hour, 0)
        except:
            slot_time = datetime.now()
        
        # Ищем матч, время начала которого максимально близко к текущему слоту
        best_match = None
        min_time_diff = timedelta.max
        
        for match in sorted_matches:
            match_time = match.get('parsed_time')
            if not match_time:
                continue
            
            # Вычисляем разницу во времени
            time_diff = abs(match_time - slot_time)
            
            # Предпочитаем матчи, которые начинаются ПОСЛЕ времени поста
            if match_time > slot_time and time_diff < min_time_diff:
                min_time_diff = time_diff
                best_match = match
        
        # Если не нашли матч, который начинается после поста, берем ближайший
        if not best_match and sorted_matches:
            best_match = sorted_matches[0]
        
        return best_match
    
    def update_match_in_db(self, match_data: Dict, analysis_result: Dict):
        """
        Обновляет информацию о матче в базе данных
        
        Args:
            match_data (Dict): Исходные данные матча
            analysis_result (Dict): Результат анализа AI
        """
        # Здесь можно добавить логику обновления данных
        # Например, обновить коэффициенты или другую информацию
        
        # Пока просто помечаем как использованный (это делает analyzer.analyze_match_by_url)
        pass
    
    def create_post_template(self, data: Dict, post_number: int) -> str:
        """Создает текст поста на основе данных и номера поста"""
        
        templates = {
            1: "🎯 *УТРЕННИЙ ПРОГНОЗ* 🎯\n\n",
            2: "📊 *ДНЕВНОЙ АНАЛИЗ* 📊\n\n",
            3: "⚡ *ВЕЧЕРНИЙ ПРОГНОЗ* ⚡\n\n",
            4: "🔮 *ОСНОВНОЙ ПРОГНОЗ* 🔮\n\n",
            5: "💎 *ПРЕМИУМ ВЫБОР* 💎\n\n",
            6: "🌙 *НОЧНОЙ МАТЧ* 🌙\n\n"
        }
        
        post = templates.get(post_number, "📈 *ПРОГНОЗ ОТ ЭКСПЕРТА* 📈\n\n")
        
        # Добавляем информацию о матче
        post += f"*{data.get('заголовок', 'Спортивный матч')}*\n"
        post += f"*Начало:* {data.get('Время начала', 'Время не указано')}\n\n"
        
        # Прогноз
        post += "🎯 *ПРОГНОЗ НА МАТЧ:*\n"
        post += f"▪️ *Ставка:* {data.get('прогноз_ставки', 'Не определено')}\n"
        post += f"▪️ *Коэффициент:* {data.get('рекомендуемый_коэффициент', 'N/A')}\n"
        post += f"▪️ *Уверенность:* {data.get('уровень_уверенности', 'N/A')}\n\n"
        
        # Анализ
        post += "📊 *АНАЛИТИКА:*\n"
        post += f"{data.get('краткая_аналитика', '')}\n\n"
        
        # Обоснование
        post += "🧠 *ОБОСНОВАНИЕ:*\n"
        post += f"{data.get('обоснование', '')}\n\n"
        
        # Риски
        risks = data.get('риски', '')
        if risks:
            post += "⚠️ *РИСКИ:*\n"
            post += f"{risks}\n\n"
        
        # Альтернативные ставки
        alt_bets = data.get('альтернативные_ставки', [])
        if alt_bets and isinstance(alt_bets, list) and len(alt_bets) > 0:
            post += "🔀 *АЛЬТЕРНАТИВЫ:*\n"
            for i, alt in enumerate(alt_bets[:3], 1):
                post += f"{i}. {alt}\n"
            post += "\n"
        
        # Мотивация
        motivation = data.get('мотив', 'Сделай правильный выбор и увеличивай свои шансы на победу!')
        post += f"🚀 *{motivation}*\n\n"
        
        # Футер
        post += "──────────────\n"
        current_time = datetime.now().strftime('%H:%M %d.%m.%Y')
        post += f"⏰ *Опубликовано:* {current_time}\n"
        
        # Хэштеги в зависимости от времени суток
        if post_number <= 2:
            post += "#утро #прогноз #ставки"
        elif post_number <= 4:
            post += "#день #анализ #ставки"
        else:
            post += "#вечер #ночь #ставки"
        
        return post
    
    def send_post(self, post_number: int, post_time: str = None, match_url: str = None) -> Tuple[bool, str]:
        """
        Отправка поста в указанное время или с указанным матчем
        
        Args:
            post_number (int): Номер поста (1-6)
            post_time (str): Время отправки (для логирования) - опционально
            match_url (str): URL матча для публикации - опционально
        
        Returns:
            Tuple[bool, str]: (Успешно ли отправлен пост, Сообщение о результате)
        """
        if not self.analyzer:
            error_msg = "Ошибка: анализатор не инициализирован"
            print(f"[{datetime.now()}] {error_msg}")
            return False, error_msg
        
        time_display = post_time if post_time else "вручную"
        print(f"[{datetime.now()}] Подготовка поста {post_number} для отправки {time_display}")
        
        # Получаем матч
        if match_url:
            # Ищем матч по URL
            match_data = None
            unused_matches = self.db.get_unused_matches(limit=100)
            for match in unused_matches:
                if match.get('url') == match_url:
                    match_data = match
                    break
            
            if not match_data:
                error_msg = f"Матч с URL {match_url} не найден в базе данных"
                print(f"[{datetime.now()}] {error_msg}")
                return False, error_msg
        else:
            # Получаем матч для временного слота
            match_data = self.get_match_for_time_slot(post_time)
        
        if not match_data:
            error_msg = f"Не удалось найти подходящий матч для поста {post_number}"
            print(f"[{datetime.now()}] {error_msg}")
            return False, error_msg
        
        match_url = match_data.get('url')
        match_title = match_data.get('title', 'Без названия')
        match_start = match_data.get('start_time', 'Время не указано')
        
        print(f"[{datetime.now()}] Выбран матч: {match_title}")
        print(f"[{datetime.now()}] Начало матча: {match_start}")
        
        try:
            # Анализируем матч (это также пометит его как использованный)
            analysis_result = self.analyzer.analyze_match_by_url(match_url)
            
            if "error" in analysis_result:
                error_msg = f"Ошибка анализа матча: {analysis_result['error']}"
                print(f"[{datetime.now()}] {error_msg}")
                return False, error_msg
            
            # Обновляем информацию о матче (если нужно)
            self.update_match_in_db(match_data, analysis_result)
            
            # Создаем текст поста
            post_text = self.create_post_template(analysis_result, post_number)
            
            # Отправляем пост
            try:
                # Формируем имя файла с изображением
                image_folder = "images"
                image_files = [
                    f"{image_folder}/post{post_number}.jpg",
                    f"{image_folder}/post{post_number}.png",
                    f"{image_folder}/post1.jpg",  # Фолбэк на первую картинку
                    f"{image_folder}/default.jpg"
                ]
                
                image_path = None
                for img_path in image_files:
                    if os.path.exists(img_path):
                        image_path = img_path
                        break
                
                if image_path:
                    with open(image_path, 'rb') as photo:
                        bot.send_photo(
                            CHANNEL_ID,
                            photo,
                            caption=post_text,
                            parse_mode='Markdown'
                        )
                    success_msg = f"Пост {post_number} успешно отправлен с изображением"
                    print(f"[{datetime.now()}] {success_msg}")
                else:
                    # Если нет изображения, отправляем только текст
                    bot.send_message(
                        CHANNEL_ID,
                        post_text,
                        parse_mode='Markdown'
                    )
                    success_msg = f"Пост {post_number} успешно отправлен без изображения"
                    print(f"[{datetime.now()}] {success_msg}")
                
                # Логируем успешную отправку
                self._log_post_success(post_number, match_url, match_title, manual=bool(post_time is None))
                return True, success_msg
                
            except Exception as e:
                error_msg = f"Ошибка отправки поста: {e}"
                print(f"[{datetime.now()}] {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Общая ошибка при обработке поста: {e}"
            print(f"[{datetime.now()}] {error_msg}")
            return False, error_msg
    
    def _log_post_success(self, post_number: int, match_url: str, match_title: str, manual: bool = False):
        """Логирование успешной отправки поста"""
        log_entry = {
            'post_number': post_number,
            'match_url': match_url,
            'match_title': match_title,
            'timestamp': datetime.now().isoformat(),
            'channel': CHANNEL_ID,
            'manual': manual
        }
        
        # Сохраняем в файл лога
        log_file = 'posting_log.json'
        logs = []
        
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except:
                logs = []
        
        logs.append(log_entry)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        print(f"[{datetime.now()}] Логирование завершено для поста {post_number}")
    
    def get_scheduled_stats(self):
        """Получение статистики по запланированным постам"""
        stats = {
            'total_matches': self.db.count_matches(),
            'unused_matches': self.db.count_matches(used=False),
            'used_matches': self.db.count_matches(used=True),
            'next_matches': len(self.get_next_matches_sorted(limit=10))
        }
        
        return stats


# Инициализация бота
bot_instance = TelegramBotWithDB()

# ========== КОМАНДЫ ДЛЯ АДМИНИСТРАТОРА ==========

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id == ADMIN_ID

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Обработчик команды /start и /help"""
    if is_admin(message.from_user.id):
        help_text = """
👋 *Добро пожаловать в панель управления ботом!*

📋 *Доступные команды:*
/post - Ручная публикация поста
/stats - Статистика базы данных
/matches - Список доступных матчей
/cancel - Отмена текущей операции

📅 *Расписание авто-публикации:*
12:00 - Утренний прогноз
14:00 - Дневной анализ
16:00 - Вечерний прогноз
18:00 - Основной прогноз
20:00 - Премиум выбор
22:00 - Ночной матч
        """
        bot.reply_to(message, help_text, parse_mode='Markdown')
    else:
        bot.reply_to(message, "⛔ У вас нет доступа к этому боту.")

@bot.message_handler(commands=['post'])
def start_manual_post(message):
    """Начало процесса ручной публикации поста"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ У вас нет прав для публикации постов.")
        return
    
    # Устанавливаем состояние пользователя
    user_states[message.from_user.id] = ManualPostState.WAITING_POST_NUMBER
    
    # Отправляем меню выбора типа поста
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    keyboard.add('1️⃣ Утренний', '2️⃣ Дневной', '3️⃣ Вечерний')
    keyboard.add('4️⃣ Основной', '5️⃣ Премиум', '6️⃣ Ночной')
    keyboard.add('❌ Отмена')
    
    bot.send_message(
        message.chat.id,
        "📝 *Ручная публикация поста*\n\n"
        "Выберите тип поста (от 1 до 6):\n\n"
        "1️⃣ - Утренний прогноз (12:00)\n"
        "2️⃣ - Дневной анализ (14:00)\n"
        "3️⃣ - Вечерний прогноз (16:00)\n"
        "4️⃣ - Основной прогноз (18:00)\n"
        "5️⃣ - Премиум выбор (20:00)\n"
        "6️⃣ - Ночной матч (22:00)",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['stats'])
def show_stats(message):
    """Показать статистику базы данных"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ У вас нет прав для просмотра статистики.")
        return
    
    stats = bot_instance.get_scheduled_stats()
    
    stats_text = f"""
📊 *Статистика базы данных:*

• Всего матчей: {stats['total_matches']}
• Неиспользованных: {stats['unused_matches']}
• Использованных: {stats['used_matches']}
• Доступно для публикации: {stats['next_matches']}

⏰ *Следующая авто-публикация:*
"""
    
    # Получаем следующую запланированную задачу
    next_run = schedule.next_run()
    if next_run:
        time_until = next_run - datetime.now()
        mins = int(time_until.total_seconds() // 60)
        secs = int(time_until.total_seconds() % 60)
        stats_text += f"Через: {mins:02d}:{secs:02d}"
    else:
        stats_text += "Нет запланированных публикаций"
    
    bot.reply_to(message, stats_text, parse_mode='Markdown')

@bot.message_handler(commands=['matches'])
def show_available_matches(message):
    """Показать список доступных матчей"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ У вас нет прав для просмотра матчей.")
        return
    
    matches = bot_instance.get_all_available_matches(limit=20)
    
    if not matches:
        bot.reply_to(message, "📭 Нет доступных матчей для публикации.")
        return
    
    matches_text = "📋 *Доступные матчи:*\n\n"
    
    for i, match in enumerate(matches[:10], 1):
        title = match.get('title', 'Без названия')[:50]
        start_time = match.get('start_time', 'Время не указано')
        matches_text += f"{i}. *{title}*\n   ⏰ {start_time}\n\n"
    
    if len(matches) > 10:
        matches_text += f"\n... и еще {len(matches) - 10} матчей"
    
    bot.reply_to(message, matches_text, parse_mode='Markdown')

@bot.message_handler(commands=['cancel'])
def cancel_operation(message):
    """Отмена текущей операции"""
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    if user_id in manual_post_data:
        del manual_post_data[user_id]
    
    # Убираем клавиатуру
    remove_keyboard = telebot.types.ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        "✅ Операция отменена.",
        reply_markup=remove_keyboard
    )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Обработка текстовых сообщений (для FSM ручной публикации)"""
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Проверяем состояние пользователя
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    
    if state == ManualPostState.WAITING_POST_NUMBER:
        handle_post_number_selection(message, text)
    
    elif state == ManualPostState.WAITING_MATCH_SELECTION:
        handle_match_selection(message, text)
    
    elif state == ManualPostState.WAITING_CONFIRMATION:
        handle_confirmation(message, text)

def handle_post_number_selection(message, text):
    """Обработка выбора номера поста"""
    user_id = message.from_user.id
    
    # Парсим номер поста из текста
    post_number = None
    if text in ['1', '1️⃣', '1️⃣ Утренний', 'Утренний']:
        post_number = 1
    elif text in ['2', '2️⃣', '2️⃣ Дневной', 'Дневной']:
        post_number = 2
    elif text in ['3', '3️⃣', '3️⃣ Вечерний', 'Вечерний']:
        post_number = 3
    elif text in ['4', '4️⃣', '4️⃣ Основной', 'Основной']:
        post_number = 4
    elif text in ['5', '5️⃣', '5️⃣ Премиум', 'Премиум']:
        post_number = 5
    elif text in ['6', '6️⃣', '6️⃣ Ночной', 'Ночной']:
        post_number = 6
    elif text == '❌ Отмена':
        cancel_operation(message)
        return
    
    if post_number is None:
        bot.reply_to(message, "❌ Пожалуйста, выберите тип поста из предложенных вариантов.")
        return
    
    # Сохраняем номер поста
    manual_post_data[user_id] = {'post_number': post_number}
    
    # Переходим к выбору матча
    user_states[user_id] = ManualPostState.WAITING_MATCH_SELECTION
    
    # Получаем доступные матчи
    matches = bot_instance.get_all_available_matches(limit=10)
    
    if not matches:
        bot.send_message(
            message.chat.id,
            "❌ Нет доступных матчей для публикации.\n\n"
            "Используйте команду /matches для просмотра списка матчей.",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )
        del user_states[user_id]
        return
    
    # Создаем клавиатуру с матчами
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    for i, match in enumerate(matches[:8], 1):
        title = match.get('title', 'Без названия')[:30]
        keyboard.add(f"{i}. {title}")
    
    keyboard.add('🎲 Случайный матч', '❌ Отмена')
    
    matches_text = "📋 *Выберите матч для публикации:*\n\n"
    
    for i, match in enumerate(matches[:8], 1):
        title = match.get('title', 'Без названия')[:50]
        start_time = match.get('start_time', 'Время не указано')
        matches_text += f"{i}. *{title}*\n   ⏰ {start_time}\n\n"
    
    bot.send_message(
        message.chat.id,
        matches_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

def handle_match_selection(message, text):
    """Обработка выбора матча"""
    user_id = message.from_user.id
    
    if text == '❌ Отмена':
        cancel_operation(message)
        return
    
    matches = bot_instance.get_all_available_matches(limit=10)
    
    if text == '🎲 Случайный матч':
        import random
        if matches:
            selected_match = random.choice(matches)
            match_url = selected_match.get('url')
            match_title = selected_match.get('title', 'Без названия')
            match_start = selected_match.get('start_time', 'Время не указано')
        else:
            bot.send_message(
                message.chat.id,
                "❌ Нет доступных матчей для выбора.",
                reply_markup=telebot.types.ReplyKeyboardRemove()
            )
            del user_states[user_id]
            return
    
    else:
        # Парсим номер матча из текста
        try:
            match_num = int(text.split('.')[0])
            if 1 <= match_num <= len(matches):
                selected_match = matches[match_num - 1]
                match_url = selected_match.get('url')
                match_title = selected_match.get('title', 'Без названия')
                match_start = selected_match.get('start_time', 'Время не указано')
            else:
                bot.reply_to(message, "❌ Пожалуйста, выберите матч из предложенного списка.")
                return
        except:
            bot.reply_to(message, "❌ Пожалуйста, выберите матч из предложенного списка.")
            return
    
    # Сохраняем данные о матче
    manual_post_data[user_id]['match_url'] = match_url
    manual_post_data[user_id]['match_title'] = match_title
    manual_post_data[user_id]['match_start'] = match_start
    
    # Переходим к подтверждению
    user_states[user_id] = ManualPostState.WAITING_CONFIRMATION
    
    # Создаем клавиатуру подтверждения
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    keyboard.add('✅ Да, опубликовать', '❌ Нет, отменить')
    
    post_number = manual_post_data[user_id]['post_number']
    post_types = {
        1: "Утренний прогноз",
        2: "Дневной анализ", 
        3: "Вечерний прогноз",
        4: "Основной прогноз",
        5: "Премиум выбор",
        6: "Ночной матч"
    }
    
    confirmation_text = f"""
📝 *Подтверждение публикации:*

• *Тип поста:* {post_types.get(post_number, f'Пост {post_number}')}
• *Матч:* {match_title}
• *Начало:* {match_start}

Вы уверены, что хотите опубликовать этот пост в канал?
    """
    
    bot.send_message(
        message.chat.id,
        confirmation_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

def handle_confirmation(message, text):
    """Обработка подтверждения публикации"""
    user_id = message.from_user.id
    
    if text == '❌ Нет, отменить':
        cancel_operation(message)
        return
    
    if text != '✅ Да, опубликовать':
        bot.reply_to(message, "❌ Пожалуйста, выберите один из предложенных вариантов.")
        return
    
    # Получаем данные для публикации
    data = manual_post_data.get(user_id)
    if not data:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка: данные не найдены. Начните заново с команды /post",
            reply_markup=telebot.types.ReplyKeyboardRemove()
        )
        del user_states[user_id]
        return
    
    post_number = data['post_number']
    match_url = data['match_url']
    
    # Убираем клавиатуру
    remove_keyboard = telebot.types.ReplyKeyboardRemove()
    bot.send_message(
        message.chat.id,
        "⏳ Публикую пост...",
        reply_markup=remove_keyboard
    )
    
    # Отправляем пост
    success, result_msg = bot_instance.send_post(
        post_number=post_number,
        match_url=match_url
    )
    
    # Отправляем результат пользователю
    if success:
        bot.send_message(
            message.chat.id,
            f"✅ {result_msg}\n\n"
            f"Пост успешно опубликован в канал!",
            parse_mode='Markdown'
        )
    else:
        bot.send_message(
            message.chat.id,
            f"❌ {result_msg}\n\n"
            f"Попробуйте выбрать другой матч или проверьте настройки бота.",
            parse_mode='Markdown'
        )
    
    # Очищаем состояние
    if user_id in user_states:
        del user_states[user_id]
    if user_id in manual_post_data:
        del manual_post_data[user_id]

# Функции для отправки постов по расписанию
def create_post_functions(bot_instance):
    """Создает функции для отправки постов по расписанию"""
    
    def send_post_12_00():
        bot_instance.send_post(1, "12:00")
    
    def send_post_14_00():
        bot_instance.send_post(2, "14:00")
    
    def send_post_16_00():
        bot_instance.send_post(3, "16:00")
    
    def send_post_18_00():
        bot_instance.send_post(4, "18:00")
    
    def send_post_20_00():
        bot_instance.send_post(5, "20:00")
    
    def send_post_22_00():
        bot_instance.send_post(6, "22:00")
    
    return [
        ("12:00", send_post_12_00),
        ("14:00", send_post_14_00),
        ("16:00", send_post_16_00),
        ("18:00", send_post_18_00),
        ("20:00", send_post_20_00),
        ("22:00", send_post_22_00)
    ]


# Настройка расписания
def setup_schedule(post_functions):
    """Настраивает расписание отправки постов"""
    for time_str, func in post_functions:
        schedule.every().day.at(time_str).do(func)
    
    print("Расписание настроено:")
    for time_str, _ in post_functions:
        print(f"{time_str} - Пост")


# Функция для запуска планировщика в отдельном потоке
def run_scheduler():
    """Запускает планировщик в отдельном потоке"""
    while True:
        schedule.run_pending()
        time.sleep(30)  # Проверка каждые 30 секунд


# Функция для запуска телеграм бота в отдельном потоке
def run_telegram_bot():
    """Запускает телеграм бота для обработки команд"""
    print("🤖 Запуск Telegram бота для ручного управления...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)


# Основной код
if __name__ == '__main__':
    print("=== Бот для публикации спортивных прогнозов ===")
    
    # Инициализация
    bot_instance.initialize_analyzer(api_key="F75pwTloHHL5ZcbrW95KWLIrpIR2wtJo")
    
    # Показываем статистику
    stats = bot_instance.get_scheduled_stats()
    print("\n📊 Статистика базы данных:")
    print(f"Всего матчей: {stats['total_matches']}")
    print(f"Неиспользованных: {stats['unused_matches']}")
    print(f"Использованных: {stats['used_matches']}")
    print(f"Доступно для публикации: {stats['next_matches']}")
    
    # Создаем функции для постов
    post_functions = create_post_functions(bot_instance)
    
    # Настраиваем расписание
    setup_schedule(post_functions)
    
    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Запуск телеграм бота в отдельном потоке
    telegram_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    telegram_thread.start()
    
    print("\n🤖 Бот запущен и ожидает времени публикации...")
    print("📱 Доступны команды для администратора:")
    print("   /post - Ручная публикация поста")
    print("   /stats - Статистика базы данных")
    print("   /matches - Список доступных матчей")
    print("   /cancel - Отмена текущей операции")
    print("\nНажмите Ctrl+C для остановки\n")
    
    # Основной цикл для отображения статуса
    try:
        while True:
            # Каждую минуту показываем следующую запланированную задачу
            next_run = schedule.next_run()
            if next_run:
                time_until = next_run - datetime.now()
                mins = int(time_until.total_seconds() // 60)
                secs = int(time_until.total_seconds() % 60)
                
                print(f"\r⏰ Следующий пост через: {mins:02d}:{secs:02d}", end="", flush=True)
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n👋 Бот остановлен пользователем")
    
    except Exception as e:
        print(f"\n\n⚠️ Ошибка в работе бота: {e}")