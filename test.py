from database import SportsDatabase


db = SportsDatabase(db_path='sports_data.db')

url = "https://kushvsporte.ru/event/6356010-shanhay-dragons-amur"

db.mark_as_unused(url)
print(url)