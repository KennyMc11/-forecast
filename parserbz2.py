import json
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
from datetime import datetime
from database import SportsDatabase
import pytz



moscow_tz = pytz.timezone('Europe/Moscow')
moscow_time_3 = datetime.now(moscow_tz)
moscow_time = moscow_time_3.replace(tzinfo=None)

class SportsParserBZ:
    def __init__(self, db_path='sports_data.db'):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.db = SportsDatabase(db_path)

    def parse_page(self, url, match_info=None):
        global moscow_time

        try:
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            result = {}
            
            if match_info:
                result.update(match_info)
            
            # Заголовок
            title_div = soup.select_one('.forecast-description h1') 
            start_data = soup.select_one('.match-review-head-date')
            result['title'] = title_div.get_text(strip=True) + ' ' + start_data.get_text(strip=True) if title_div else ''
            
            # Время начала
            start_time = soup.select_one('.match-review-head-scores')
            result['start_time'] = start_time.get_text(strip=True) if start_time else ''
            
            # Картинки
            team_images = []
            seen_images = set()
            
            img_tags = soup.select('.match-review-head-logo-img')
            if not img_tags:
                img_tags = soup.select('img[src*="/images/team/big/"]')
            
            for img in img_tags:
                src = img.get('src')
                if src:
                    full_url = urljoin(url, src)
                    if full_url not in seen_images:
                        team_images.append(full_url)
                        seen_images.add(full_url)
                        if len(team_images) >= 2:
                            break
            
            if len(team_images) < 2:
                team_blocks = soup.select('div.text-center')
                for block in team_blocks:
                    img = block.select_one('img[src*="/images/team/"]')
                    if img:
                        src = img.get('src')
                        if src:
                            full_url = urljoin(url, src)
                            if full_url not in seen_images:
                                team_images.append(full_url)
                                seen_images.add(full_url)
                                if len(team_images) >= 2:
                                    break
            
            result['team_images'] = team_images
            
            # Коэффициенты
            coefficients = 'Нет'
            
            result['coefficients'] = coefficients
            
            # Текст
            seotext_div1 = soup.find('div', class_='gray-block forecast-info')
            seotext_div = seotext_div1.find('p')
            full_text = seotext_div.get_text(' ', strip=True) if seotext_div else ""
            result['full_text'] = full_text
            result['has_full_text'] = bool(full_text.strip())
            
            result['url'] = url
            result['parsed_at'] = moscow_time.isoformat()
            
            return result
            
        except Exception as e:
            print(f"Ошибка при парсинге {url}: {e}")
            return None
        
    def process_urls_from_json(self, json_file):
        """Парсинг URL из JSON файла и сохранение в БД"""
        with open(json_file, 'r', encoding='utf-8') as f:
            matches = json.load(f)
        
        urls = [match['url'] for match in matches]
        
        success_count = 0
        skip_count = 0
        
        for i, url in enumerate(urls):
            print(f"Парсинг {i+1}/{len(urls)}: {url}")
            
            data = self.parse_page(url)
            if data:
                if not data.get('full_text'):
                    print(f"  ✗ Пропущено: отсутствует full_text")
                    skip_count += 1
                    continue
                
                if self.db.save_match(data):
                    print(f"  ✓ Сохранено в БД")
                    success_count += 1
                else:
                    print(f"  ✗ Ошибка сохранения в БД")
            else:
                print(f"  ✗ Ошибка парсинга")
        
        total_count = self.db.count_matches()
        unused_count = self.db.count_matches(used=False)
        
        print(f"\nГотово!")
        print(f"Успешно обработано: {success_count}")
        print(f"Пропущено (без текста): {skip_count}")
        print(f"Всего в БД: {total_count} записей")
        print(f"Неиспользованных: {unused_count}")
        
        return success_count
    
    def parse_and_save_single(self, url):
        """Парсинг и сохранение одной страницы"""
        print(f"Парсинг: {url}")
        
        data = self.parse_page(url)
        if data:
            if not data.get('full_text'):
                print(f"  ✗ Пропущено: отсутствует full_text")
                return None
            
            if self.db.save_match(data):
                print(f"  ✓ Сохранено в БД")
                return data
            else:
                print(f"  ✗ Ошибка сохранения в БД")
                return None
        else:
            print(f"  ✗ Ошибка парсинга")
            return None
        
    def delete_old_events(self, days_old=0):
        """
        Удаление событий из БД и картинок, если они добавлены раньше чем сегодня
        
        Args:
            days_old: количество дней (события старше этого срока будут удалены)
                       По умолчанию 1 день (вчерашние и более старые события)
        """
        print(f"\n--- Удаление старых событий (старше {days_old} дня) ---")
        
        deleted_count = self.db.delete_past_events(days_old)
        
        if deleted_count > 0:
            print(f"Удалено {deleted_count} событий, добавленных до сегодняшнего дня")
        else:
            print("Нет событий для удаления")
        
        return deleted_count
    
if __name__ == "__main__":
    # Создаем парсер
    parser = SportsParserBZ()

    # УДАЛЯЕМ старые события перед парсингом новых
    parser.delete_old_events(days_old=0)
    
    # Парсим страницы из JSON файла
    results = parser.process_urls_from_json('events.json')
    
    # Пример работы с БД через объект parser.db
    print("\n--- Работа с базой данных ---")
    
    # Получить все неиспользованные записи
    unused_matches = parser.db.get_unused_matches()
    print(f"Неиспользованных записей: {len(unused_matches)}")
    
    # Пометить первую запись как использованную
    #if unused_matches:
    #    parser.db.mark_as_used(unused_matches[0]['url'])
    #    print(f"Запись {unused_matches[0]['url']} помечена как использованная")
    
    # Получить статистику
    total = parser.db.count_matches()
    used = parser.db.count_matches(used=True)
    unused = parser.db.count_matches(used=False)
    print(f"Статистика: Всего={total}, Использовано={used}, Неиспользовано={unused}")