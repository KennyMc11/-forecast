import pytz
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import json
import csv
import os


# Создаем объект временной зоны для Москвы
moscow_tz = pytz.timezone('Europe/Moscow')
moscow_time_3 = datetime.now(moscow_tz)
moscow_time = moscow_time_3.replace(tzinfo=None)

def parse_events(url, max_events=10):
    try:
        # Отправляем GET-запрос
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Проверяем успешность запроса

        # Создаем объект BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # Находим все блоки с классом 'top-event-block border-block mb-3'
        sides_blocks = soup.find_all('div', class_='col-12 bets-description-card-block col-md-6')

        events = []
        seen_titles = set()  # Множество для отслеживания уникальных заголовков

        for block in sides_blocks:
            link = block.find('a', class_='bets-description-card')

            if len(events) >= max_events:
                break

            if link:
                # Извлекаем href
                href = link.get('href')
                
                # Извлекаем title
                title = link.get('data-match-name', '') + ' ' + link.get('data-tournament', '')

                if title in seen_titles:
                    continue  # Пропускаем дубликат
                seen_titles.add(title)  # Добавляем title в множество

                match_name = link.get('data-match-name', '')

                # Формируем полный URL
                full_url = urljoin(url, href)

                event_datetime_nf1 = block.find('div', class_='bets-description-card__match-info__description')
                event_datetime_nf = event_datetime_nf1.text.strip() if event_datetime_nf1 else ''

                # Добавляем дату и время события
                event_datetime = extract_datetime_from_title(event_datetime_nf)

                events.append({
                    'match_name': match_name,
                    'title': title,
                    'url': full_url,
                    'relative_url': href,
                    'event_datetime': event_datetime  # Добавляем datetime события
                })
        return events

    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе: {e}")
        return []
    except Exception as e:
        print(f"Ошибка при парсинге: {e}")
        return []
            

def extract_datetime_from_title(event_datetime_nf):
    """Извлекает дату и время из строки event_datetime_nf"""
    
    global moscow_time

    # Нормализуем строку
    title_lower = event_datetime_nf.lower().replace('ё', 'е').strip()
    
    # Попробуем найти формат "день месяц время" (например: "3 января 15:30")
    pattern1 = r'(\d{1,2})\s+([а-я]+)\s+(\d{1,2}:\d{2})'
    match1 = re.search(pattern1, title_lower)
    
    if match1:
        day_str, month_name, time_str = match1.groups()
        day = int(day_str)
        
        # Словарь для преобразования русских названий месяцев
        months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        
        month = months.get(month_name)
        
        if month:
            # Нормализуем время
            if ':' in time_str:
                hours, minutes = time_str.split(':')
                time_str = f"{int(hours):02d}:{int(minutes):02d}"
            
            current_year = moscow_time.year
            current_month = moscow_time.month
            
            # Определяем год
            year = current_year
            if month < current_month or (month == current_month and day < moscow_time.day):
                year = current_year + 1
            
            try:
                time_obj = datetime.strptime(time_str, '%H:%M')
                return datetime(year, month, day, time_obj.hour, time_obj.minute)
            except ValueError:
                return datetime(year, month, day, 0, 0)
    
    # Попробуем найти формат "дд.мм.гггг" (например: "03.01.2026")
    pattern2 = r'(\d{2})\.(\d{2})\.(\d{4})'
    match2 = re.search(pattern2, event_datetime_nf)
    
    if match2:
        day, month, year = map(int, match2.groups())
        
        # Попробуем найти время
        time_pattern = r'(\d{1,2}:\d{2})'
        time_match = re.search(time_pattern, event_datetime_nf)
        
        if time_match:
            time_str = time_match.group(1)
            if ':' in time_str:
                hours, minutes = time_str.split(':')
                time_str = f"{int(hours):02d}:{int(minutes):02d}"
            try:
                time_obj = datetime.strptime(time_str, '%H:%M')
                return datetime(year, month, day, time_obj.hour, time_obj.minute)
            except ValueError:
                return datetime(year, month, day, 0, 0)
        else:
            return datetime(year, month, day, 0, 0)
    
    # Если не удалось распарсить
    return datetime.max


def filter_events(events, min_hours_before=1):
    """
    Фильтрует события, исключая уже начавшиеся и те, до которых осталось менее min_hours_before часов
    """
    # Получаем текущее время в Москва
    now1 = datetime.now(ZoneInfo('Europe/Moscow'))
    now = now1.replace(tzinfo=None)
    
    print(f"Текущее время (UTC+5): {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Минимальное время до события: {min_hours_before} часов")

    filtered_events = []
    
    for event in events:
        event_datetime = event.get('event_datetime')
        
        # Пропускаем события без даты или с datetime.max
        if not event_datetime or event_datetime == datetime.max:
            continue
            
        # Вычисляем разницу во времени
        time_difference = event_datetime - now
        
        # Проверяем условия
        if time_difference.total_seconds() > 0:
            hours_before = time_difference.total_seconds() / 3600
            if hours_before >= min_hours_before:
                # Добавляем информацию о времени до события
                event['hours_until'] = round(hours_before, 1)
                event['starts_in'] = str(time_difference).split('.')[0]
                event['event_time'] = event_datetime.strftime('%Y-%m-%d %H:%M')
                filtered_events.append(event)
                print(f"✓ Сохраняем: {event.get('title')} - через {hours_before:.1f} часов")
            else:
                print(f"✗ Отфильтровано (менее {min_hours_before} часов): {event.get('title')} - через {hours_before:.1f} часов")
        else:
            print(f"✗ Отфильтровано (уже началось): {event.get('title')} - началось {abs(time_difference.total_seconds()/3600):.1f} часов назад")
    
    return filtered_events


def save_to_json(events, filename='events.json'):
    """Сохраняет результаты в JSON файл, отсортированные по дате и времени"""
    # Фильтруем события
    filtered_events = filter_events(events, min_hours_before=1)
    
    # Сортируем события по дате и времени
    sorted_events = sorted(
        filtered_events, 
        key=lambda x: x.get('event_datetime', datetime.min)
    )
    
    # Создаем копию для JSON (преобразуем datetime в строки)
    events_for_json = []
    for event in sorted_events:
        event_copy = event.copy()
        if 'event_datetime' in event_copy:
            event_copy['event_datetime'] = event_copy['event_datetime'].strftime('%Y-%m-%d %H:%M:%S')
        events_for_json.append(event_copy)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(events_for_json, f, ensure_ascii=False, indent=2)


def save_to_csv(events, filename='events.csv'):
    """Сохраняет результаты в CSV файл"""
    # Фильтруем события (передаем исходные события)
    filtered_events = filter_events(events, min_hours_before=1)
    
    # Сортируем события по дате и времени
    sorted_events = sorted(
        filtered_events, 
        key=lambda x: x.get('event_datetime', datetime.min)
    )
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Номер', 'Дата и время', 'Название события', 
                         'Полная ссылка', 'До начала (часов)', 'До начала'])
        
        for i, event in enumerate(sorted_events, 1):
            event_time = event.get('event_time', '')
            writer.writerow([
                i,
                event_time,
                event['title'],
                event['url'],
                event.get('hours_until', ''),
                event.get('starts_in', '')
            ])


def delete_file(file_path):
    """
    Удаляет файл по указанному пути
    """
    try:
        os.remove(file_path)
        print(f"Файл '{file_path}' успешно удален")
        return True
    except FileNotFoundError:
        print(f"Ошибка: файл '{file_path}' не найден")
        return False
    except PermissionError:
        print(f"Ошибка: нет прав на удаление файла '{file_path}'")
        return False
    except OSError as e:
        print(f"Ошибка при удалении файла '{file_path}': {e}")
        return False
    

def parserbz():
    delete_file("events.json")
    delete_file("events.csv")

    url = "https://betzona.ru/"
    
    print(f"Парсим сайт: {url}")
    print("=" * 50)
    
    events = parse_events(url, max_events=10)
    
    if events:
        print(f"Найдено событий: {len(events)}")
        print("=" * 50)
        
        # Выводим информацию о всех событиях для отладки
        print("Все найденные события:")
        for i, event in enumerate(events, 1):
            event_datetime = event.get('event_datetime')
            if event_datetime and event_datetime != datetime.max:
                time_str = event_datetime.strftime('%Y-%m-%d %H:%M')
                print(f"{i}. {event['title']}")
                print(f"   Время: {time_str}")
                print(f"   Ссылка: {event['url']}")
                print()
        
        # Сохраняем результаты
        save_to_json(events)
        save_to_csv(events)
        
        print(f"\nРезультаты сохранены в файлы:")
        print(f"  - events.json")
        print(f"  - events.csv")
    else:
        print("События не найдены")


if __name__ == "__main__":
    parserbz()