import sqlite3
import json
from datetime import datetime, timedelta
import pytz
import os
from PIL import Image
import io
import requests


# Создаем объект временной зоны для Москвы
moscow_tz = pytz.timezone('Europe/Moscow')
moscow_time_3 = datetime.now(moscow_tz)
moscow_time = moscow_time_3.replace(tzinfo=None)

class SportsDatabase:
    def __init__(self, db_path='sports_data.db', images_dir='team_images'):
        self.db_path = db_path
        self.images_dir = images_dir
        self.init_database()
        
        # Создаем директорию для изображений, если она не существует
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir)
    
    def init_database(self):
        """Инициализация базы данных и создание таблицы"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                start_time TEXT,
                team_images TEXT,  -- JSON массив URL изображений
                combined_image_path TEXT,  -- Путь к склеенному изображению
                coefficients TEXT, -- JSON объект с коэффициентами
                full_text TEXT,
                parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                has_full_text BOOLEAN DEFAULT 0,
                used BOOLEAN DEFAULT 0  -- 0 = False, 1 = True
            )
        ''')
        
        # Создаем индекс для быстрого поиска по URL
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_matches_url ON matches(url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_matches_used ON matches(used)')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Получение соединения с базой данных"""
        return sqlite3.connect(self.db_path)
    
    def download_image(self, url):
        """Загрузка изображения по URL"""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content))
        except Exception as e:
            print(f"Ошибка при загрузке изображения {url}: {e}")
            return None
    
    def combine_team_images(self, image_urls, match_id):
        """
        Склеивает два изображения команд с гарантированно белым фоном и большими отступами
        
        Args:
            image_urls: список из 2 URL изображений
            match_id: ID матча
        
        Returns:
            Путь к сохраненному склеенному изображению
        """
        if len(image_urls) != 2:
            print(f"Ожидалось 2 изображения, получено {len(image_urls)}")
            return None
        
        try:
            # Загружаем оба изображения
            images = []
            
            for i, url in enumerate(image_urls):
                img = self.download_image(url)
                if img:
                    print(f"Загружено изображение {i+1}: {img.size}, режим: {img.mode}")
                    
                    # Ключевое исправление: правильно обрабатываем прозрачность
                    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                        # Создаем новое изображение с белым фоном
                        white_bg = Image.new('RGB', img.size, (255, 255, 255))
                        
                        # Если есть альфа-канал, используем его как маску
                        if img.mode == 'RGBA':
                            # Конвертируем RGBA в RGB с белым фоном
                            white_bg.paste(img, mask=img.split()[3])  # Альфа-канал
                        elif img.mode == 'LA':
                            # LA = L (яркость) + A (альфа)
                            white_bg.paste(img.convert('RGBA'), mask=img.split()[1])
                        elif img.mode == 'P':
                            # P = палитра с прозрачностью
                            img = img.convert('RGBA')
                            white_bg.paste(img, mask=img.split()[3])
                        
                        img = white_bg
                    elif img.mode != 'RGB':
                        # Для других режимов просто конвертируем
                        img = img.convert('RGB')
                    
                    images.append(img)
                else:
                    # Создаем заглушку с белым фоном
                    placeholder = Image.new('RGB', (150, 150), (255, 255, 255))
                    images.append(placeholder)
                    print(f"Создан placeholder для изображения {i+1}")
            
            # Уменьшаем размер изображений для лучшего восприятия
            TARGET_HEIGHT = 200  # Маленькая высота для изображений
            
            # НАСТРОЙКИ ОТСТУПОВ - УВЕЛИЧИЛИ ЗДЕСЬ
            SIDE_PADDING = 140   # Большие отступы слева и справа (было 60)
            TOP_BOTTOM_PADDING = 40  # Отступы сверху и снизу (было 60)
            SPACING = 60         # Расстояние между изображениями (было 40)
            
            # Ресайзим с сохранением пропорций
            resized_images = []
            for img in images:
                # Вычисляем новые размеры
                ratio = TARGET_HEIGHT / img.height
                new_width = int(img.width * ratio)
                
                # Качественный ресайзинг
                resized = img.resize((new_width, TARGET_HEIGHT), 
                                    Image.Resampling.LANCZOS)
                resized_images.append(resized)
            
            # Создаем белый холст
            total_image_width = sum(img.width for img in resized_images)
            
            # Увеличиваем ширину холста за счет больших боковых отступов
            canvas_width = total_image_width + (SIDE_PADDING * 2) + SPACING
            canvas_height = TARGET_HEIGHT + (TOP_BOTTOM_PADDING * 2)
            
            # Создаем абсолютно белый фон
            canvas = Image.new('RGB', (canvas_width, canvas_height), (255, 255, 255))
            
            # Размещаем изображения по центру с увеличенными отступами
            x_offset = SIDE_PADDING
            y_offset = TOP_BOTTOM_PADDING
            
            for i, img in enumerate(resized_images):
                # Вставляем изображение на белый фон
                canvas.paste(img, (x_offset, y_offset))
                
                # Добавляем очень тонкую серую границу для лучшего восприятия (опционально)
                from PIL import ImageDraw
                draw = ImageDraw.Draw(canvas)
                border_color = (240, 240, 240)  # Очень светлый серый
                draw.rectangle([x_offset-1, y_offset-1, 
                            x_offset+img.width, y_offset+img.height], 
                            outline=border_color, width=1)
                
                x_offset += img.width + SPACING
            
            # Сохраняем
            filename = f"match_{match_id}_teams.jpg"
            filepath = os.path.join(self.images_dir, filename)
            
            # Сохраняем с максимальным качеством
            canvas.save(filepath, 'JPEG', quality=100, optimize=True)
            
            print(f"Склеенное изображение сохранено: {filepath}")
            print(f"Размер холста: {canvas.size}, Размеры изображений: {[img.size for img in resized_images]}")
            print(f"Отступы: слева/справа={SIDE_PADDING}px, сверху/снизу={TOP_BOTTOM_PADDING}px")
            
            return filepath
            
        except Exception as e:
            print(f"Ошибка при склеивании изображений: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def save_match(self, data):
        """Сохранение данных матча в базу данных"""
        global moscow_time
        if not data:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Сначала проверяем, существует ли уже запись
            cursor.execute('SELECT id, used FROM matches WHERE url = ?', (data['url'],))
            existing = cursor.fetchone()
            
            team_images = data.get('team_images', [])
            combined_image_path = None
            
            # Если есть изображения команд и их ровно 2, склеиваем их
            if len(team_images) == 2:
                if existing:
                    match_id = existing[0]
                else:
                    # Получаем следующий ID для нового матча
                    cursor.execute('SELECT MAX(id) FROM matches')
                    max_id_result = cursor.fetchone()
                    match_id = (max_id_result[0] or 0) + 1
                
                # Создаем склеенное изображение
                combined_image_path = self.combine_team_images(team_images, match_id)
            
            if existing:
                # Если запись уже существует, обновляем данные, но сохраняем флаг used
                cursor.execute('''
                    UPDATE matches SET 
                    title = ?, 
                    start_time = ?, 
                    team_images = ?, 
                    combined_image_path = ?,
                    coefficients = ?, 
                    full_text = ?, 
                    parsed_at = ?, 
                    has_full_text = ?
                    WHERE url = ?
                ''', (
                    data.get('title', ''),
                    data.get('start_time', ''),
                    json.dumps(team_images),
                    combined_image_path,
                    json.dumps(data.get('coefficients', {})),
                    data.get('full_text', ''),
                    data.get('parsed_at', moscow_time.isoformat()),
                    data.get('has_full_text', False),
                    data['url']
                ))
                match_id = existing[0]
            else:
                # Если записи нет, создаем новую с used = 0
                cursor.execute('''
                    INSERT INTO matches 
                    (url, title, start_time, team_images, combined_image_path, coefficients, full_text, parsed_at, has_full_text, used)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ''', (
                    data['url'],
                    data.get('title', ''),
                    data.get('start_time', ''),
                    json.dumps(team_images),
                    combined_image_path,
                    json.dumps(data.get('coefficients', {})),
                    data.get('full_text', ''),
                    data.get('parsed_at', moscow_time.isoformat()),
                    data.get('has_full_text', False)
                ))
                match_id = cursor.lastrowid
            
            conn.commit()
            
            # Если у нас еще нет склеенного изображения (например, для существующей записи),
            # но есть ссылки на изображения, создаем его
            if not combined_image_path and len(team_images) == 2 and match_id:
                combined_image_path = self.combine_team_images(team_images, match_id)
                if combined_image_path:
                    cursor.execute('''
                        UPDATE matches SET combined_image_path = ? WHERE id = ?
                    ''', (combined_image_path, match_id))
                    conn.commit()
            
            return True
            
        except Exception as e:
            print(f"Ошибка при сохранении в БД: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def mark_as_used(self, url):
        """Пометить запись как использованную"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('UPDATE matches SET used = 1 WHERE url = ?', (url,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Ошибка при обновлении статуса: {e}")
            return False
        finally:
            conn.close()
    
    def mark_as_unused(self, url):
        """Пометить запись как неиспользованную"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('UPDATE matches SET used = 0 WHERE url = ?', (url,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Ошибка при обновлении статуса: {e}")
            return False
        finally:
            conn.close()
    
    def get_unused_matches(self, limit=None):
        """Получить неиспользованные записи"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row  # Для доступа к полям по имени
        cursor = conn.cursor()
        
        try:
            query = 'SELECT * FROM matches WHERE used = 0'
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Преобразуем строки в словари
            matches = []
            for row in rows:
                match_dict = dict(row)
                # Декодируем JSON поля
                match_dict['team_images'] = json.loads(match_dict['team_images']) if match_dict['team_images'] else []
                match_dict['coefficients'] = json.loads(match_dict['coefficients']) if match_dict['coefficients'] else {}
                matches.append(match_dict)
            
            return matches
        finally:
            conn.close()
    
    def get_used_matches(self, limit=None):
        """Получить использованные записи"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            query = 'SELECT * FROM matches WHERE used = 1'
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            matches = []
            for row in rows:
                match_dict = dict(row)
                match_dict['team_images'] = json.loads(match_dict['team_images']) if match_dict['team_images'] else []
                match_dict['coefficients'] = json.loads(match_dict['coefficients']) if match_dict['coefficients'] else {}
                matches.append(match_dict)
            
            return matches
        finally:
            conn.close()
    
    def get_match_by_url(self, url):
        """Получить запись по URL"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute('SELECT * FROM matches WHERE url = ?', (url,))
            row = cursor.fetchone()
            
            if row:
                match_dict = dict(row)
                match_dict['team_images'] = json.loads(match_dict['team_images']) if match_dict['team_images'] else []
                match_dict['coefficients'] = json.loads(match_dict['coefficients']) if match_dict['coefficients'] else {}
                return match_dict
            return None
        finally:
            conn.close()
    
    def get_all_matches(self, limit=None):
        """Получить все записи"""
        conn = self.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            query = 'SELECT * FROM matches ORDER BY parsed_at DESC'
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            matches = []
            for row in rows:
                match_dict = dict(row)
                match_dict['team_images'] = json.loads(match_dict['team_images']) if match_dict['team_images'] else []
                match_dict['coefficients'] = json.loads(match_dict['coefficients']) if match_dict['coefficients'] else {}
                matches.append(match_dict)
            
            return matches
        finally:
            conn.close()
    
    def delete_match(self, url):
        """Удалить запись по URL"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Сначала получаем путь к изображению, чтобы удалить его
            cursor.execute('SELECT combined_image_path FROM matches WHERE url = ?', (url,))
            result = cursor.fetchone()
            
            # Удаляем файл изображения, если он существует
            if result and result[0] and os.path.exists(result[0]):
                try:
                    os.remove(result[0])
                    print(f"Удален файл изображения: {result[0]}")
                except Exception as e:
                    print(f"Ошибка при удалении файла изображения: {e}")
            
            # Удаляем запись из БД
            cursor.execute('DELETE FROM matches WHERE url = ?', (url,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Ошибка при удалении: {e}")
            return False
        finally:
            conn.close()
    
    def delete_past_events(self, days_old=0):
        """
        Удаление прошедших событий старше указанного количества дней
        
        Args:
            days_old: количество дней (события старше этого срока будут удалены)
        """
        global moscow_time

        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Вычисляем дату, старше которой события считаются прошедшими
            cutoff_date = (moscow_time - timedelta(days=days_old)).strftime('%Y-%m-%d')
            
            # Получаем пути к изображениям, которые будут удалены
            cursor.execute('''
                SELECT combined_image_path FROM matches 
                WHERE DATE(parsed_at) < DATE(?)
            ''', (cutoff_date,))
            
            # Удаляем файлы изображений
            for row in cursor.fetchall():
                if row[0] and os.path.exists(row[0]):
                    try:
                        os.remove(row[0])
                    except Exception as e:
                        print(f"Ошибка при удалении файла {row[0]}: {e}")
            
            # Удаляем события из БД
            cursor.execute('''
                DELETE FROM matches 
                WHERE DATE(parsed_at) < DATE(?)
            ''', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            print(f"Удалено прошедших событий: {deleted_count}")
            return deleted_count
            
        except Exception as e:
            print(f"Ошибка при удалении прошедших событий: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def count_matches(self, used=None):
        """Подсчитать количество записей"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            if used is None:
                cursor.execute('SELECT COUNT(*) FROM matches')
            else:
                cursor.execute('SELECT COUNT(*) FROM matches WHERE used = ?', (1 if used else 0,))
            
            return cursor.fetchone()[0]
        finally:
            conn.close()
    
    def clear_database(self):
        """Очистить всю базу данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Удаляем все файлы изображений
            cursor.execute('SELECT combined_image_path FROM matches')
            for row in cursor.fetchall():
                if row[0] and os.path.exists(row[0]):
                    try:
                        os.remove(row[0])
                    except Exception as e:
                        print(f"Ошибка при удалении файла {row[0]}: {e}")
            
            # Очищаем таблицу
            cursor.execute('DELETE FROM matches')
            conn.commit()
            print("База данных очищена")
        finally:
            conn.close()