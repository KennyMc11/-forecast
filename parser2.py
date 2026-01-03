import json
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin


def parse_coefficients_precise(btn_element):
    """Точный парсинг коэффициентов из кнопки"""
    # Метод 1: Ищем span с классом black-color (это коэффициент)
    coeff_span = btn_element.select_one('span.black-color')
    if not coeff_span:
        return None, None
    
    coefficient = coeff_span.get_text(strip=True)
    
    # Метод 2: Находим название ставки (все, что не коэффициент)
    # Клонируем элемент, удаляем span с коэффициентом
    btn_clone = BeautifulSoup(str(btn_element), 'html.parser')
    for span in btn_clone.select('span.black-color'):
        span.decompose()
    
    # Получаем оставшийся текст - это название ставки
    bet_name = btn_clone.get_text(strip=True)
    
    # Очищаем название
    bet_name = bet_name.replace(' ', '').strip()
    
    return bet_name, coefficient

class SportsParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
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
            if title_div:
                result['title'] = title_div.get_text(strip=True)

            #Время начала
            start_time = soup.select_one('.color888.time-title')
            if start_time:
                result['time'] = start_time.get_text(strip=True)
            
            # Картинки
            team_images = []
            seen_images = set()  # Множество для отслеживания уникальных URL
            
            # Вариант 1: Более специфичный селектор
            img_tags = soup.select('div.row.align-items-center.mb-4 img.img-fluid.mt-2.mb-2')
            
            # Вариант 2: Если первый вариант не находит, пробуем другой
            if not img_tags:
                img_tags = soup.select('img[src*="/images/team/big/"]')
            
            for img in img_tags:
                src = img.get('src')
                if src:
                    full_url = urljoin(url, src)
                    # Проверяем, не добавляли ли уже эту картинку
                    if full_url not in seen_images:
                        team_images.append(full_url)
                        seen_images.add(full_url)
                        
                        # Ограничиваем максимум 2 картинки (по одной на команду)
                        if len(team_images) >= 2:
                            break
            
            # Если все еще не нашли картинки, пробуем третий вариант
            if len(team_images) < 2:
                # Ищем картинки в блоке с командами
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
            
            # Коэффициенты - ТОЧНЫЙ МЕТОД
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
            result['full_text'] = seotext_div.get_text(' ', strip=True) if seotext_div else ""
            
            result['url'] = url
            
            return result
            
        except Exception as e:
            print(f"Ошибка при парсинге {url}: {e}")
            return None
    
    def process_urls_from_json(self, json_file, output_dir='parsed_data'):
        """Альтернативная версия: использует только URL из JSON"""
        os.makedirs(output_dir, exist_ok=True)
        
        with open(json_file, 'r', encoding='utf-8') as f:
            matches = json.load(f)
        
        # Извлекаем только URL из вашей структуры
        urls = [match['url'] for match in matches]
        
        results = []
        
        for i, url in enumerate(urls):
            print(f"Парсинг {i+1}/{len(urls)}: {url}")
            
            data = self.parse_page(url)
            if data:
                if not data.get('full_text'):
                    print(f"  ✗ Пропущено: отсутствует full_text")
                    continue
                
                results.append(data)
                
                filename = f"result_{i+1}.json"
                filepath = os.path.join(output_dir, filename)
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                print(f"  ✓ Сохранено в {filename}")
        
        # Сохраняем все результаты в один файл
        all_results_path = os.path.join(output_dir, 'all_results.json')
        with open(all_results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\nГотово! Всего обработано: {len(results)} страниц")
        print(f"Результаты сохранены в папке: {output_dir}")
        
        return results

# Пример использования
if __name__ == "__main__":
    # Создаем парсер
    parser = SportsParser()
    
    # Пример JSON файла с URL (создайте его сами)
    # urls.json должен содержать массив URL:
    # [
    #     "https://kushvsporte.ru/event/6347741-kalyari-milan",
    #     "другие URL..."
    # ]
    
    # Парсим страницы
    results = parser.process_urls_from_json('events.json')
    
    # Или парсим одну страницу для теста
    # test_url = "https://kushvsporte.ru/event/6347741-kalyari-milan"
    # result = parser.parse_page(test_url)
    # print(json.dumps(result, ensure_ascii=False, indent=2))