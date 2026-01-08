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
import pytz
from parser import parser
from parser2 import SportsParser

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

moscow_tz = pytz.timezone('Europe/Moscow')

def get_moscow_time():
    """Возвращает текущее время в Москве как naive datetime"""
    moscow_time = datetime.now(moscow_tz)
    return moscow_time.replace(tzinfo=None)

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
        now = get_moscow_time()
        
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
        return match_time > get_moscow_time() - timedelta(minutes=30)


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
            now = get_moscow_time()
            slot_time = datetime(now.year, now.month, now.day, slot_hour, 0)
        except:
            slot_time = get_moscow_time()
        
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
        
        #post = templates.get(post_number, "📈 *ПРОГНОЗ ОТ ЭКСПЕРТА* 📈\n\n")
        
        # Добавляем информацию о матче
        post = f"✅*{data.get('заголовок', 'Спортивный матч')}*\n"
        post += f"*Начало:* {data.get('Время начала', 'Время не указано')} по Москве\n\n"
        
        # Прогноз
        post += "🎯 *ПРОГНОЗ НА МАТЧ:*\n"
        post += f"▪️ *Ставка:* {data.get('прогноз_ставки', 'Не определено')}\n"
        post += f"▪️ *Коэффициент:* {data.get('рекомендуемый_коэффициент', 'N/A')}\n"
        post += f"▪️ *Уверенность:* {data.get('уровень_уверенности', 'N/A')}\n\n"

        # Анализ
        post += "*АНАЛИЗ:*\n"
        post += f"{data.get('краткая_аналитика', '')}\n"
        
        # Обоснование
        post += "*ОБОСНОВАНИЕ:*\n"
        post += f"{data.get('обоснование', '')}\n"
        
        # Риски
        risks = data.get('риски', '')
        if risks:
            post += f"*РИСКИ:*\n"
            post += f"{risks}\n\n"
        
        # Альтернативные ставки
        alt_bets = data.get('альтернативные_ставки', [])
        if alt_bets and isinstance(alt_bets, list) and len(alt_bets) > 0:
            post += "🔀 *АЛЬТЕРНАТИВЫ:*\n"
            for i, alt in enumerate(alt_bets[:3], 1):
                post += f"{i}. {alt}\n"
            post += "\n"
        
        # Футер
        post += "──────────────\n"

        # Мотивация
        motivation = data.get('мотив', 'Сделай правильный выбор и увеличивай свои шансы на победу!')
        post += f"🚀 *{motivation}*\n\nПромокод *KENNY*\n\n*Актуальные ссылки:*\nССЫЛКА РФ\nССЫЛКА СНГ\n\n"

        
        # Хэштеги в зависимости от времени суток
        if post_number <= 2:
            post += "#аналитика #утро #прогноз #ставки"
        elif post_number <= 4:
            post += "#пргноз #день #анализ #ставки"
        else:
            post += "#прогноз #вечер #ночь #ставки"
        
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

        current_time = get_moscow_time()

        if not self.analyzer:
            error_msg = "Ошибка: анализатор не инициализирован"
            print(f"[{current_time}] {error_msg}")
            return False, error_msg
        
        time_display = post_time if post_time else "вручную"
        print(f"[{get_moscow_time()}] Подготовка поста {post_number} для отправки {time_display}")
        
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
                print(f"[{get_moscow_time()}] {error_msg}")
                return False, error_msg
        else:
            # Получаем матч для временного слота
            match_data = self.get_match_for_time_slot(post_time)
        
        if not match_data:
            error_msg = f"Не удалось найти подходящий матч для поста {post_number}"
            print(f"[{get_moscow_time()}] {error_msg}")
            return False, error_msg
        
        match_url = match_data.get('url')
        match_title = match_data.get('title', 'Без названия')
        match_start = match_data.get('start_time', 'Время не указано')
        
        print(f"[{get_moscow_time()}] Выбран матч: {match_title}")
        print(f"[{get_moscow_time()}] Начало матча: {match_start}")
        
        try:
            # Анализируем матч (это также пометит его как использованный)
            analysis_result = self.analyzer.analyze_match_by_url(match_url)
            
            if "error" in analysis_result:
                error_msg = f"Ошибка анализа матча: {analysis_result['error']}"
                print(f"[{get_moscow_time()}] {error_msg}")
                return False, error_msg
            
            # Обновляем информацию о матче (если нужно)
            self.update_match_in_db(match_data, analysis_result)
            
            # Создаем текст поста
            post_text = self.create_post_template(analysis_result, post_number)
            
            # Отправляем пост
            try:
                # Формируем имя файла с изображением
                image_folder = "team_images"
                image_files = [
                    f"{image_folder}/match_{post_number}_teams.jpg",
                    f"{image_folder}/match_{post_number}_teams.png",
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
                    print(f"[{get_moscow_time()}] {success_msg}")
                else:
                    # Если нет изображения, отправляем только текст
                    bot.send_message(
                        CHANNEL_ID,
                        post_text,
                        parse_mode='Markdown'
                    )
                    success_msg = f"Пост {post_number} успешно отправлен без изображения"
                    print(f"[{get_moscow_time()}] {success_msg}")
                
                # Логируем успешную отправку
                self._log_post_success(post_number, match_url, match_title, manual=bool(post_time is None))
                return True, success_msg
                
            except Exception as e:
                error_msg = f"Ошибка отправки поста: {e}"
                print(f"[{get_moscow_time()}] {error_msg}")
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Общая ошибка при обработке поста: {e}"
            print(f"[{get_moscow_time()}] {error_msg}")
            return False, error_msg
    
    def _log_post_success(self, post_number: int, match_url: str, match_title: str, manual: bool = False):
        """Логирование успешной отправки поста"""
        current_time = get_moscow_time()
        log_entry = {
            'post_number': post_number,
            'match_url': match_url,
            'match_title': match_title,
            'timestamp': current_time.isoformat(),
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
        
        print(f"[{get_moscow_time()}] Логирование завершено для поста {post_number}")
    
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
/parser - Обновить ссылки событий на актуальные
/parser2 - Обновить БД(удалить старые записи, записать новые)
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
        # Получаем текущее время в московском часовом поясе
        current_moscow = datetime.now(moscow_tz)
        
        # Конвертируем время следующего запуска в московское время
        # schedule использует локальное время сервера
        if next_run.tzinfo is None:
            # Если время без часового пояса, считаем что это локальное время сервера
            # Добавляем часовой пояс сервера
            try:
                import tzlocal
                server_tz = tzlocal.get_localzone()
                next_run_local = server_tz.localize(next_run)
                next_run_moscow = next_run_local.astimezone(moscow_tz)
            except:
                # Если не удалось определить часовой пояс сервера, предполагаем UTC
                next_run_local = pytz.UTC.localize(next_run)
                next_run_moscow = next_run_local.astimezone(moscow_tz)
        else:
            next_run_moscow = next_run.astimezone(moscow_tz)
        
        # Вычисляем разницу
        time_until = next_run_moscow - current_moscow
        
        if time_until.total_seconds() > 0:
            mins = int(time_until.total_seconds() // 60)
            secs = int(time_until.total_seconds() % 60)
            stats_text += f"Через: {mins:02d}:{secs:02d}"
        else:
            # Если время уже прошло, показываем когда следующий пост
            stats_text += f"\r⏰ Ожидание следующего поста по расписанию"
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

@bot.message_handler(commands=['parser'])
def cancel_operation(message):
    """Парсинг главной"""
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    if user_id in manual_post_data:
        del manual_post_data[user_id]
    
    parser()

    bot.send_message(
        message.chat.id,
        "Ссылки событий обновлены"
    )

@bot.message_handler(commands=['parser2'])
def cancel_operation(message):
    """Парсинг ссылок"""
    if not is_admin(message.from_user.id):
        return
    
    user_id = message.from_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    if user_id in manual_post_data:
        del manual_post_data[user_id]
    
    # Отправляем сообщение о начале загрузки
    loading_msg = bot.send_message(message.chat.id, "⏳ Начинается процесс парсинга... Пожалуйста, подождите.")
    
    try:
        # Создаем парсер
        parser = SportsParser()
        
        # Обновляем сообщение о статусе
        bot.edit_message_text(
            "🗑️ Удаление старых событий...",
            message.chat.id,
            loading_msg.message_id
        )
        
        # УДАЛЯЕМ старые события перед парсингом новых
        parser.delete_old_events(days_old=0)
        
        # Обновляем сообщение о статусе
        bot.edit_message_text(
            "🌐 Парсинг страниц из JSON файла...",
            message.chat.id,
            loading_msg.message_id
        )
        
        # Парсим страницы из JSON файла
        results = parser.process_urls_from_json('events.json')
        
        # Обновляем сообщение о статусе
        bot.edit_message_text(
            "📊 Получение статистики...",
            message.chat.id,
            loading_msg.message_id
        )
        
        # Получить статистику
        total = parser.db.count_matches()
        used = parser.db.count_matches(used=True)
        unused = parser.db.count_matches(used=False)

        # Удаляем сообщение о загрузке и отправляем финальное сообщение
        bot.delete_message(message.chat.id, loading_msg.message_id)
        
        bot.send_message(
            message.chat.id,
            f"✅ Парсинг завершен!\n"
            f"Старые события удалены.\n"
            f"БД и картинки обновлены\n\n"
            f"📈 Статистика:\n"
            f"• Всего событий: {total}\n"
            f"• Использовано: {used}\n"
            f"• Неиспользовано: {unused}"
        )
        
    except Exception as e:
        # В случае ошибки обновляем сообщение об ошибке
        bot.edit_message_text(
            f"❌ Произошла ошибка при парсинге:\n{str(e)}",
            message.chat.id,
            loading_msg.message_id
        )
        import traceback
        traceback.print_exc()

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
    """Настраивает расписание отправки постов с учетом разницы часовых поясов"""
    print("Настройка расписания...")
    
    # Определяем разницу между временем сервера и московским временем
    server_time = datetime.now()
    moscow_time = get_moscow_time()
    
    # Вычисляем разницу в часах
    time_diff = moscow_time - server_time
    hours_diff = time_diff.total_seconds() / 3600
    
    print(f"Разница между временем сервера и московским: {hours_diff:.1f} часов")
    
    # Если сервер в UTC (разница +3 часа), корректируем время
    adjusted_times = {}
    for time_str, func in post_functions:
        hour, minute = map(int, time_str.split(':'))
        
        if abs(hours_diff) > 0.5:  # Если разница больше 30 минут
            # Корректируем время для schedule
            adjusted_hour = hour - int(hours_diff)
            if adjusted_hour < 0:
                adjusted_hour += 24
            elif adjusted_hour >= 24:
                adjusted_hour -= 24
            adjusted_time = f"{adjusted_hour:02d}:{minute:02d}"
        else:
            adjusted_time = time_str
        
        schedule.every().day.at(adjusted_time).do(func)
        adjusted_times[time_str] = adjusted_time
        print(f"  {time_str} MSK → {adjusted_time} (время сервера)")
    
    return adjusted_times

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
    
    while True:
        try:
            print("Подключение к Telegram API...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60, interval=3)
        except Exception as e:
            print(f"Ошибка подключения к Telegram API: {e}")
            print("Повторная попытка через 10 секунд...")
            time.sleep(10)


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
    adjusted_schedule = setup_schedule(post_functions)
    
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
            # Получаем время до следующего поста
            next_run = schedule.next_run()
            
            if next_run:
                # Вычисляем разницу в секундах
                time_until = next_run - datetime.now()
                
                if time_until.total_seconds() > 0:
                    # ПРАВИЛЬНЫЙ расчет часов, минут, секунд
                    total_seconds = int(time_until.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    
                    # Определяем номер поста по часу
                    hour = next_run.hour
                    if hour == 7 or hour == 12:
                        post_num = "1️⃣"
                    elif hour == 9 or hour == 14:
                        post_num = "2️⃣"
                    elif hour == 11 or hour == 16:
                        post_num = "3️⃣"
                    elif hour == 13 or hour == 18:
                        post_num = "4️⃣"
                    elif hour == 15 or hour == 20:
                        post_num = "5️⃣"
                    elif hour == 17 or hour == 22:
                        post_num = "6️⃣"
                    else:
                        post_num = "?"
                    
                    # Формируем строку времени
                    if hours > 0:
                        time_display = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        time_display = f"{minutes:02d}:{seconds:02d}"
                    
                    print(f"\r⏰ Пост {post_num} через: {time_display}", end="", flush=True)
                else:
                    print(f"\r⏰ Ожидание следующего поста", end="", flush=True)
            else:
                print(f"\r⏰ Нет запланированных постов", end="", flush=True)
            
            time.sleep(1)
                
    except KeyboardInterrupt:
        print("\n\n👋 Бот остановлен пользователем")
    
    except Exception as e:
        print(f"\n\n⚠️ Ошибка в работе бота: {e}")