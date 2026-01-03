import json
import os
from datetime import datetime
from mistralai import Mistral

class SportPredictionAnalyzer:
    """Класс для анализа спортивных прогнозов с использованием AI"""
    
    def __init__(self, api_key):
        """
        Инициализация анализатора
        
        Args:
            api_key (str): API ключ для Mistral
        """
        self.client = Mistral(api_key=api_key)
        self.model = "mistral-medium"
        
    def analyze_single_file(self, json_file_path):
        """
        Анализ одного JSON файла
        
        Args:
            json_file_path (str): Путь к JSON файлу
        
        Returns:
            dict: Результат анализа
        """
        return self._analyze_data(json_file_path)
    
    def analyze_multiple_files(self, directory_path):
        """
        Анализ всех JSON файлов в директории
        
        Args:
            directory_path (str): Путь к директории с JSON файлами
        
        Returns:
            dict: Словарь с результатами анализа всех файлов
        """
        results = {}
        
        # Ищем все JSON файлы в директории
        for filename in os.listdir(directory_path):
            if filename.endswith('.json'):
                file_path = os.path.join(directory_path, filename)
                print(f"Анализирую файл: {filename}")
                
                try:
                    result = self._analyze_data(file_path)
                    results[filename] = result
                except Exception as e:
                    results[filename] = {"error": str(e)}
        
        return results
    
    def _analyze_data(self, json_file_path):
        """
        Внутренний метод анализа данных
        
        Args:
            json_file_path (str): Путь к JSON файлу
        
        Returns:
            dict: Результат анализа
        """
        # Чтение данных из файла
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Извлечение данных
        title = data.get("title", "")
        coefficients = data.get("coefficients", {})
        full_text = data.get("full_text", "")
        
        # Формирование промпта
        user_content = self._create_prompt(title, coefficients, full_text)
        
        # Отправка запроса к AI
        response = self.client.chat.complete(
            model=self.model,
            messages=[
                {
                    "role": "system", 
                    "content": """Ты - профессиональный спортивный аналитик с 10-летним опытом в букмекерской сфере. 
                    Анализируй предоставленные данные и давай обоснованные прогнозы. 
                    Отвечай ТОЛЬКО в формате JSON."""
                },
                {"role": "user", "content": user_content}
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"}
        )
        
        # Парсинг ответа
        ai_response = response.choices[0].message.content
        result = json.loads(ai_response)
        
        # Добавление метаданных
        result["meta"] = {
            "source_file": json_file_path,
            "analysis_date": datetime.now().isoformat(),
            "model_used": self.model
        }
        
        return result
    
    def _create_prompt(self, title, coefficients, full_text):
        """
        Создание промпта для AI
        
        Args:
            title (str): Заголовок матча
            coefficients (dict): Коэффициенты
            full_text (str): Полный текст анализа
        
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
    "краткая_аналитика": "1-2 предложения с ключевыми факторами",
    "прогноз_ставки": "конкретная ставка (например: 'П2 в основное время', 'Тотал больше 5.5' и тому подобные)",
    "обоснование": "развернутое обоснование выбора (1-2 предложения)",
    "рекомендуемый_коэффициент": "коэффициент, на который стоит делать ставку",
    "уровень_уверенности": "число от 1 до 10, где 10 - максимальная уверенность(напрример: '9/10')",
    "риски": "основные риски для данной ставки(1 предложение)",
    "альтернативные_ставки": ["альтернатива 1", "альтернатива 2"],
    "мотивация": "текст мотивируйщий перейти по ссылке ниже на сайт букмекера и сдлеать ставку(1 короткое, продающее предложение) "
}}

Будь объективным и основывай прогноз только на предоставленных данных."""
        
        return prompt


# Пример использования класса
if __name__ == "__main__":
    # Инициализация анализатора
    analyzer = SportPredictionAnalyzer(api_key="F75pwTloHHL5ZcbrW95KWLIrpIR2wtJo")
    
    # Анализ одного файла
    result = analyzer.analyze_single_file("parsed_data/result_1.json")
    
    # Вывод результата
    print("Результат анализа:")
    print(json.dumps(result, indent=2, ensure_ascii=False))