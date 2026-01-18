from database import SportsDatabase


db = SportsDatabase(db_path='sports_data.db')

url = "https://kushvsporte.ru/event/6381447-aston-villa-everton"

db.mark_as_unused(url)
print(url)