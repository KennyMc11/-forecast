import sqlite3
import json
from datetime import datetime


class SportsDatabase:
    def __init__(self, db_path='sports_data.db'):
        self.db_path = db_path
        self.init_database()
    
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
    
    def save_match(self, data):
        """Сохранение данных матча в базу данных"""
        if not data:
            return False
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO matches 
                (url, title, start_time, team_images, coefficients, full_text, parsed_at, has_full_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['url'],
                data.get('title', ''),
                data.get('start_time', ''),
                json.dumps(data.get('team_images', [])),
                json.dumps(data.get('coefficients', {})),
                data.get('full_text', ''),
                data.get('parsed_at', datetime.now().isoformat()),
                data.get('has_full_text', False)
            ))
            
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
            cursor.execute('DELETE FROM matches WHERE url = ?', (url,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Ошибка при удалении: {e}")
            return False
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
            cursor.execute('DELETE FROM matches')
            conn.commit()
            print("База данных очищена")
        finally:
            conn.close()