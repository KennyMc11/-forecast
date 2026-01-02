import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
from datetime import datetime


def parse_events(url):
    """
    Парсит сайт и извлекает ссылки событий из блоков с классом 'col-6 col-sm-3 sides'
    """
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
        sides_blocks = soup.find_all('div', class_='top-event-block border-block mb-3')
        
        events = []
        
        for block in sides_blocks:
            # Внутри блока ищем ссылку
            link = block.find('a', class_='notUnderlineHover')
            
            if link:
                # Извлекаем href
                href = link.get('href')
                
                # Извлекаем title
                title = link.get('title', '')
                
                # Извлекаем названия команд
                spans = link.find_all('span')
                teams = [span.text.strip() for span in spans if span.text.strip()]
                
                # Формируем название матча
                if len(teams) >= 2:
                    match_name = f"{teams[0]} - {teams[1]}"
                elif teams:
                    match_name = teams[0]
                else:
                    match_name = 'Без названия'
                
                # Формируем полный URL
                full_url = urljoin(url, href)
                
                events.append({
                    'match_name': match_name,
                    'title': title,
                    'url': full_url,
                    'relative_url': href,
                    'team1': teams[0] if len(teams) > 0 else '',
                    'team2': teams[1] if len(teams) > 1 else ''
                })
            
        return events
        
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при запросе: {e}")
        return []
    except Exception as e:
        print(f"Ошибка при парсинге: {e}")
        return []


def extract_datetime_from_title(title):
    """Извлекает дату и время из строки title"""
    # Ищем паттерн "день месяц время" в строке title
    pattern = r'(\d{1,2}\s+[а-яё]+)\s+(\d{1,2}:\d{2})'
    match = re.search(pattern, title.lower())
    
    if match:
        date_str, time_str = match.groups()
        
        # Словарь для преобразования русских названий месяцев
        months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        
        # Парсим день и месяц
        day = int(date_str.split()[0])
        month_name = date_str.split()[1]
        month = months.get(month_name.lower())
        
        if month:
            # Создаем объект datetime (год берем текущий)
            current_year = datetime.now().year
            time_obj = datetime.strptime(time_str, '%H:%M')
            
            return datetime(current_year, month, day, 
                           time_obj.hour, time_obj.minute)
    
    # Если не удалось распарсить, возвращаем дату далекого прошлого
    return datetime.min


def save_to_json(events, filename='events.json'):
    """Сохраняет результаты в JSON файл, отсортированные по дате и времени"""
    
    # Сортируем события по дате и времени из title
    sorted_events = sorted(
        events, 
        key=lambda x: extract_datetime_from_title(x.get('title', ''))
    )
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(sorted_events, f, ensure_ascii=False, indent=2)


def save_to_csv(events, filename='events.csv'):
    """Сохраняет результаты в CSV файл"""
    import csv
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Номер', 'Название события', 'Полная ссылка', 'Относительная ссылка'])
        
        for i, event in enumerate(events, 1):
            writer.writerow([i, event['title'], event['url'], event['relative_url']])

def main():
    url = "https://kushvsporte.ru/freeforcats"
    
    print(f"Парсим сайт: {url}")
    events = parse_events(url)
    
    if events:
        print(f"Найдено событий: {len(events)}")
        print("=" * 50)
        
        for i, event in enumerate(events, 1):
            print(f"{i}. {event['title']}")
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
    main()