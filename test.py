from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from parser import extract_datetime_from_title
import json
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin

now1 = datetime.now(ZoneInfo('Asia/Yekaterinburg'))
now = now1.replace(tzinfo=None)

title = "Прогнозы на матч Астон Вилла - Ноттингем Форест 03 января 15:30"
time = extract_datetime_from_title(title)

timediff = time - now

print(time)
print(now)

print(timediff)