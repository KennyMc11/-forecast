import json
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
from datetime import datetime
from database import SportsDatabase


def parse_coefficients_precise(btn_element):
    """Точный парсинг коэффициентов из кнопки"""
    coeff_span = btn_element.select_one('span.black-color')
    if not coeff_span:
        return None, None
    
    coefficient = coeff_span.get_text(strip=True)
    
    btn_clone = BeautifulSoup(str(btn_element), 'html.parser')
    for span in btn_clone.select('span.black-color'):
        span.decompose()
    
    bet_name = btn_clone.get_text(strip=True)
    bet_name = bet_name.replace(' ', '').strip()
    
    return bet_name, coefficient


class SportsParser:
    def __init__(self, db_path='sports_data.db'):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.db = SportsDatabase(db_path)
    
    def parse_page(self, url, match_info=None):
        """Парсит одну страницу с точным извлечением коэффициентов"""
        try:
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            result = {}
            
            if match_info:
                result.update(match_info)
            
            # Заголовок
            title_div = soup.select_one('.row.align-items-center.mb-3 h1')
            result['title'] = title_div.get_text(strip=True) if title_div else ''
            
            # Время начала
            start_time = soup.select_one('.color888.time-title')
            result['start_time'] = start_time.get_text(strip=True) if start_time else ''
            
            # Картинки
            team_images = []
            seen_images = set()
            
            img_tags = soup.select('div.row.align-items-center.mb-4 img.img-fluid.mt-2.mb-2')
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
            coefficients = {}
            bet_slide = soup.select_one('#bets_carousel-slide-0')
            if bet_slide:
                for btn in bet_slide.select('a.btn.buttonKs.col'):
                    bet_name, coeff = parse_coefficients_precise(btn)
                    if bet_name and coeff:
                        coefficients[bet_name] = coeff
            
            result['coefficients'] = coefficients
            
            # Текст
            seotext_div = soup.select_one('.seotext.border-block.my-3.my-lg-4')
            full_text = seotext_div.get_text(' ', strip=True) if seotext_div else ""
            result['full_text'] = full_text
            result['has_full_text'] = bool(full_text.strip())
            
            result['url'] = url
            result['parsed_at'] = datetime.now().isoformat()
            
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


# Пример использования
if __name__ == "__main__":
    # Создаем парсер
    parser = SportsParser()
    
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