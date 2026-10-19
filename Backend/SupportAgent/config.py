import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent      # Backend/
KB_DIR = BASE_DIR / "KnowledgeBase"
ROUTER_MODEL = os.getenv("ROUTER_MODEL", "claude-sonnet-5-5")
ROUTER_MAX_TURNS = 5
