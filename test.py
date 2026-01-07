from database import SportsDatabase


db = SportsDatabase(db_path='sports_data.db')

url = "https://kushvsporte.ru/event/6356868-fulhem-chelsi"

db.mark_as_unused(url)
print(url)