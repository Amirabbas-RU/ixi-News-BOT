
import set_path
from dotenv import load_dotenv
import os
import json

#---------------------------------<< load data >>---------------------------------
load_dotenv(dotenv_path=os.path.join(set_path.base_path, "main.env"))

NEWS_UPDATE_INTERVAL_MINUTES = int(os.getenv("NEWS_UPDATE_INTERVAL_MINUTES", 60))

DB_NAME = os.getenv("DB_NAME", "news_storage.db")
DB_PATH = os.path.join(set_path.base_path, DB_NAME) 

REUTERS_RSS_URL     = os.getenv("REUTERS_RSS_URL")
CNBC_RSS_URL        = os.getenv("CNBC_RSS_URL")
INVESTING_RSS_URL   = os.getenv("INVESTING_RSS_URL")
YAHOO_RSS_URL       = os.getenv("YAHOO_RSS_URL")
FOREXFACTORY_CALENDAR_URL = os.getenv("FOREXFACTORY_CALENDAR_URL")

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL    = os.getenv("OPENAI_MODEL")

OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL    = os.getenv("OPENROUTER_MODEL")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL")

TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")
BOT_PANEL_BOT_TOKEN = os.getenv("BOT_PANEL_BOT_TOKEN", "")

MIN_IMPACT_SCORE    = int(os.getenv("MIN_IMPACT_SCORE", 7))
MAX_POSTS_PER_DAY   = int(os.getenv("MAX_POSTS_PER_DAY", 10))
RESET_DATABASE      = os.getenv("RESET_DATABASE", "false").strip().lower() == "true"
BOT_PANEL           = os.getenv("BOT_PANEL", "false").strip().lower() == "true"


HIGH_IMPACT_KEYWORDS = json.loads(os.getenv("HIGH_IMPACT_KEYWORDS"))
SOURCE_SCORE = json.loads(os.getenv("SOURCE_SCORE") ) 
