import json
import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
from datetime import datetime
from database import SportsDatabase
import pytz



moscow_tz = pytz.timezone('Europe/Moscow')
moscow_time_3 = datetime.now(moscow_tz)
moscow_time = moscow_time_3.replace(tzinfo=None)


