import json
from datetime import datetime
from mistralai import Mistral
from database import SportsDatabase  # Импортируем наш класс для работы с БД
import pytz

class SportPredictionAnalyzer:
    """Обновленный класс для анализа с фокусом на конверсию"""
    
    def __init__(self, api_key, db_path='sports_data.db'):
        self.client = Mistral(api_key=api_key)
        self.model = "mistral-medium"
        self.db = SportsDatabase(db_path)
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        
    def _get_current_moscow_time(self):
        """Получает актуальное время в Москве в момент вызова"""
        return datetime.now(self.moscow_tz).replace(tzinfo=None)

    def analyze_match_by_url(self, url):
        match_data = self.db.get_match_by_url(url)
        if not match_data:
            return {"error": f"Матч не найден"}
        
        try:
            result = self._analyze_match_data(match_data)
            result["match_url"] = url
            self.db.mark_as_used(url)
            return result
        except Exception as e:
            return {"error": str(e), "match_url": url}

    def _analyze_match_data(self, match_data):
        # Берем время ПРЯМО СЕЙЧАС
        current_time = self._get_current_moscow_time()

        title = match_data.get("title", "")
        start_time = match_data.get("start_time", "")
        full_text = match_data.get("full_text", "")
        
        coefficients_json = match_data.get("coefficients", "{}")
        try:
            coefficients = json.loads(coefficients_json) if isinstance(coefficients_json, str) else coefficients_json
        except:
            coefficients = {}
        
        user_content = self._create_prompt(title, coefficients, full_text, start_time)
        
        response = self.client.chat.complete(
            model=self.model,
            messages=[
                {
                    "role": "system", 
                    "content": """Ты - профессиональный каппер с жестким стилем. Твоя задача: проанализировать матч и выдать точный прогноз. 
                    Твой текст должен мотивировать человека сделать ставку по твоей ссылке. 
                    Пиши уверенно, используй термины разные термины каперов, типа: 'железо', 'банк'.
                    Отвечай СТРОГО в формате JSON."""
                },
                {"role": "user", "content": user_content}
            ],
            temperature=0.8, # Немного снизил для стабильности прогнозов
            max_tokens=800,
            response_format={"type": "json_object"})
        
        ai_response = response.choices[0].message.content
        result = json.loads(ai_response)
        
        # Метаданные с правильной датой
        result["meta"] = {
            "analysis_date": current_time.isoformat(),
            "model_used": self.model
        }
        
        return result
    
    def _create_prompt(self, title, coefficients, full_text, start_time):
        return f"""Анализ матча: {title}
                    Начало: {start_time}
                    Кэфы: {json.dumps(coefficients, ensure_ascii=False)}
                    Данные: {full_text[:3000]} # Ограничил объем данных для экономии токенов

                    Верни JSON:
                    {{
                        "заголовок": "{title}",
                        "Время начала": "{start_time}",
                        "краткая_аналитика": "2 четких предложения: почему эта ставка зайдет.",
                        "прогноз_ставки": "конкретный исход (например: Тотал Больше 2.5)",
                        "обоснование": "1 мощный аргумент.",
                        "рекомендуемый_коэффициент": "число (например: 1.95)",
                        "уровень_уверенности": "например: 9/10",
                        "риски": "1 предложение, что может пойти не так",
                        "альтернативные_ставки": ["исход 1", "исход 2"],
                        "мотив": "Короткий призыв (до 7 слов) забрать бонус в закрепе или по ссылке."
                    }}
                    """

    def get_statistics(self):
        """Статистика для админ-панели"""
        try:
            total = self.db.count_matches()
            unused = self.db.count_matches(used=False)
            return {
                "total": total,
                "unused": unused,
                "used": total - unused
            }
        except:
            return {"total": 0, "unused": 0, "used": 0}


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