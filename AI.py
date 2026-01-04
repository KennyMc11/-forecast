import json
from datetime import datetime
from mistralai import Mistral
from database import SportsDatabase  # Импортируем наш класс для работы с БД


class SportPredictionAnalyzer:
    """Класс для анализа спортивных прогнозов с использованием AI"""
    
    def __init__(self, api_key, db_path='sports_data.db'):
        """
        Инициализация анализатора
        
        Args:
            api_key (str): API ключ для Mistral
            db_path (str): Путь к базе данных SQLite
        """
        self.client = Mistral(api_key=api_key)
        self.model = "mistral-medium"
        self.db = SportsDatabase(db_path)
        
    def analyze_unused_matches(self, limit=None):
        """
        Анализ всех неиспользованных матчей из базы данных
        
        Args:
            limit (int, optional): Ограничение количества матчей для анализа
        
        Returns:
            list: Список результатов анализа
        """
        # Получаем неиспользованные матчи из БД
        unused_matches = self.db.get_unused_matches(limit=limit)
        results = []
        
        print(f"Найдено {len(unused_matches)} неиспользованных матчей для анализа")
        
        for i, match_data in enumerate(unused_matches):
            print(f"\nАнализирую матч {i+1}/{len(unused_matches)}:")
            print(f"  Заголовок: {match_data.get('title', 'Без названия')}")
            print(f"  URL: {match_data.get('url', '')}")
            
            try:
                # Анализируем матч
                result = self._analyze_match_data(match_data)
                
                # Добавляем URL матча для связи
                result["match_url"] = match_data.get('url', '')
                
                # Помечаем матч как использованный
                self.db.mark_as_used(match_data.get('url', ''))
                
                results.append(result)
                
                print(f"  ✓ Успешно проанализирован")
                print(f"  Прогноз: {result.get('прогноз_ставки', 'Не определен')}")
                print(f"  Уверенность: {result.get('уровень_уверенности', 'N/A')}")
                
            except Exception as e:
                error_result = {
                    "error": str(e),
                    "match_url": match_data.get('url', ''),
                    "title": match_data.get('title', '')
                }
                results.append(error_result)
                print(f"  ✗ Ошибка анализа: {e}")
        
        return results
    
    def analyze_match_by_url(self, url):
        """
        Анализ конкретного матча по URL
        
        Args:
            url (str): URL матча
        
        Returns:
            dict: Результат анализа
        """
        # Получаем данные матча из БД
        match_data = self.db.get_match_by_url(url)
        
        if not match_data:
            return {"error": f"Матч с URL {url} не найден в базе данных"}
        
        print(f"Анализирую матч:")
        print(f"  Заголовок: {match_data.get('title', 'Без названия')}")
        
        try:
            result = self._analyze_match_data(match_data)
            result["match_url"] = url
            
            # Помечаем как использованный
            self.db.mark_as_used(url)
            
            print(f"  ✓ Успешно проанализирован")
            return result
            
        except Exception as e:
            return {
                "error": str(e),
                "match_url": url,
                "title": match_data.get('title', '')
            }
    
    def analyze_all_matches(self, limit=None, mark_as_used=True):
        """
        Анализ всех матчей из базы данных
        
        Args:
            limit (int, optional): Ограничение количества матчей
            mark_as_used (bool): Помечать ли матчи как использованные после анализа
        
        Returns:
            list: Список результатов анализа
        """
        # Получаем все матчи из БД
        all_matches = self.db.get_all_matches(limit=limit)
        results = []
        
        print(f"Анализирую {len(all_matches)} матчей из базы данных")
        
        for i, match_data in enumerate(all_matches):
            print(f"\nМатч {i+1}/{len(all_matches)}:")
            print(f"  Заголовок: {match_data.get('title', 'Без названия')}")
            
            try:
                result = self._analyze_match_data(match_data)
                result["match_url"] = match_data.get('url', '')
                result["was_used"] = bool(match_data.get('used', 0))
                
                if mark_as_used:
                    self.db.mark_as_used(match_data.get('url', ''))
                
                results.append(result)
                print(f"  ✓ Успешно проанализирован")
                
            except Exception as e:
                error_result = {
                    "error": str(e),
                    "match_url": match_data.get('url', ''),
                    "title": match_data.get('title', '')
                }
                results.append(error_result)
                print(f"  ✗ Ошибка: {e}")
        
        return results
    
    def _analyze_match_data(self, match_data):
        """
        Внутренний метод анализа данных матча
        
        Args:
            match_data (dict): Данные матча из БД
        
        Returns:
            dict: Результат анализа
        """
        # Извлечение данных
        title = match_data.get("title", "")
        start_time = match_data.get("start_time", "")
        full_text = match_data.get("full_text", "")
        
        # Получаем коэффициенты из JSON строки
        coefficients_json = match_data.get("coefficients", "{}")
        try:
            if isinstance(coefficients_json, str):
                coefficients = json.loads(coefficients_json)
            else:
                coefficients = coefficients_json
        except:
            coefficients = {}
        
        # Формирование промпта
        user_content = self._create_prompt(title, coefficients, full_text, start_time)
        
        # Отправка запроса к AI
        response = self.client.chat.complete(
            model=self.model,
            messages=[
                {
                    "role": "system", 
                    "content": """Ты - профессиональный спортивный аналитик с 10-летним опытом в букмекерской сфере. 
                    Анализируй предоставленные данные и давай обоснованные прогнозы. Отвечай так, чтобы вызывать доверие у пользователей, обращайся на Ты если это уместно.
                    Отвечай ТОЛЬКО в формате JSON."""
                },
                {"role": "user", "content": user_content}
            ],
            temperature=0.9,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        # Парсинг ответа
        ai_response = response.choices[0].message.content
        result = json.loads(ai_response)
        
        # Добавление метаданных
        result["meta"] = {
            "analysis_date": datetime.now().isoformat(),
            "model_used": self.model,
            "parsed_at": match_data.get("parsed_at", "")
        }
        
        return result
    
    def _create_prompt(self, title, coefficients, full_text, start_time):
        """
        Создание промпта для AI
        
        Args:
            title (str): Заголовок матча
            coefficients (dict): Коэффициенты
            full_text (str): Полный текст анализа
            start_time (str): Время начала
        
        Returns:
            str: Сформированный промпт
        """
        prompt = f"""На основе следующей информации о спортивном матче предоставь анализ и прогноз:

                    ЗАГОЛОВОК: {title}

                    КОЭФФИЦИЕНТЫ БУКМЕКЕРОВ:
                    {json.dumps(coefficients, ensure_ascii=False, indent=2)}

                    ПОЛНЫЙ АНАЛИЗ МАТЧА:
                    {full_text}

                    Проанализируй эту информацию и предоставь ответ в следующем JSON формате:
                    {{
                        "заголовок": "{title}",
                        "Время начала": "{start_time} по Москве (НЕ МЕНЯТЬ)",
                        "краткая_аналитика": "1-2 предложения с ключевыми факторами",
                        "прогноз_ставки": "конкретная ставка (например: 'П2 в основное время', 'Тотал больше 5.5' и тому подобные)",
                        "обоснование": "развернутое обоснование выбора (1-2 предложения)",
                        "рекомендуемый_коэффициент": "коэффициент, на который стоит делать ставку",
                        "уровень_уверенности": "число от 1 до 10, где 10 - максимальная уверенность(напрример: '9/10')",
                        "риски": "основные риски для данной ставки(1 предложение)",
                        "альтернативные_ставки": ["альтернатива 1", "альтернатива 2"],
                        "мотив": "текст стимулирующий перейти по ссылке ниже на сайт букмекера и сделать ставку(1 очень короткое, но очень емкое, продающее предложение)"
                    }}

                    Будь объективным и основывай прогноз только на предоставленных данных."""
        
        return prompt
    
    def save_analysis_results(self, results, output_file="analysis_results.json"):
        """
        Сохранение результатов анализа в JSON файл
        
        Args:
            results (list): Список результатов анализа
            output_file (str): Имя выходного файла
        """
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\nРезультаты анализа сохранены в файл: {output_file}")
    
    def get_statistics(self):
        """
        Получение статистики по базе данных
        
        Returns:
            dict: Статистика
        """
        total = self.db.count_matches()
        used = self.db.count_matches(used=True)
        unused = self.db.count_matches(used=False)
        
        return {
            "total_matches": total,
            "used_matches": used,
            "unused_matches": unused,
            "usage_percentage": round((used / total * 100), 2) if total > 0 else 0
        }


# Пример использования класса
if __name__ == "__main__":
    # Инициализация анализатора
    analyzer = SportPredictionAnalyzer(
        api_key="F75pwTloHHL5ZcbrW95KWLIrpIR2wtJo",
        db_path='sports_data.db'
    )
    
    print("=== Статистика базы данных ===")
    stats = analyzer.get_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    #print("\n=== Анализ неиспользованных матчей ===")
    
    # Вариант 1: Анализ только неиспользованных матчей
    #results = analyzer.analyze_unused_matches(limit=3)  # Проанализировать 3 неиспользованных матча
    
    # Вариант 2: Анализ конкретного матча по URL
    # result = analyzer.analyze_match_by_url("https://kushvsporte.ru/event/6347741-kalyari-milan")
    # results = [result]
    
    # Вариант 3: Анализ всех матчей
    # results = analyzer.analyze_all_matches(limit=5)
    
    # Сохранение результатов
    #if results:
        #analyzer.save_analysis_results(results, "ai_analysis_results.json")
        
        # Вывод первого результата
        #print("\n=== Пример результата анализа ===")
        #if isinstance(results[0], dict) and "error" not in results[0]:
        #    sample_result = results[0]
        #    print(f"Заголовок: {sample_result.get('заголовок', 'N/A')}")
        #    print(f"Время начала: {sample_result.get('Время начала', 'N/A')}")
        #    print(f"Прогноз ставки: {sample_result.get('прогноз_ставки', 'N/A')}")
        #    print(f"Уверенность: {sample_result.get('уровень_уверенности', 'N/A')}")
        #    print(f"Обоснование: {sample_result.get('обоснование', 'N/A')}")
        #else:
        #    print(f"Ошибка: {results[0].get('error', 'Неизвестная ошибка')}")
    
    # Обновленная статистика
    print("\n=== Обновленная статистика ===")
    new_stats = analyzer.get_statistics()
    for key, value in new_stats.items():
        print(f"{key}: {value}")