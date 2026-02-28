import os
import time

_ENV = {}
_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                _ENV[k.strip()] = v.strip()

GROQ_API_KEY = _ENV.get("GROQ_API_KEY", os.environ.get("GROQ_API_KEY", ""))
DATABASE_URL = _ENV.get("DATABASE_URL", os.environ.get("DATABASE_URL", ""))
FLASK_SECRET = _ENV.get("FLASK_SECRET", os.urandom(24).hex())

TB_PRESETS = [
    {"key": "cloud", "label": "ThingsBoard Cloud",       "url": "https://thingsboard.cloud",   "desc": "Official cloud — create a free account at thingsboard.cloud"},
    {"key": "demo",  "label": "ThingsBoard Demo Server", "url": "https://demo.thingsboard.io", "desc": "Public demo — use tenant@thingsboard.org / tenant"},
    {"key": "self",  "label": "My Own Server",           "url": "",                            "desc": "Self-hosted or company ThingsBoard installation"},
    {"key": "pe",    "label": "ThingsBoard PE / Edge",   "url": "",                            "desc": "Professional Edition or Edge deployment"},
]

TIME_RANGES = {
    "1h":  ("Last 1 Hour",    1),
    "6h":  ("Last 6 Hours",   6),
    "24h": ("Last 24 Hours",  24),
    "3d":  ("Last 3 Days",    72),
    "7d":  ("Last 7 Days",    168),
    "30d": ("Last 30 Days",   720),
    "3m":  ("Last 3 Months",  2160),
    "6m":  ("Last 6 Months",  4320),
    "1y":  ("Last 1 Year",    8760),
}

def get_time_bounds(rk):
    h = TIME_RANGES[rk][1]
    end = int(time.time() * 1000)
    return end - h * 3_600_000, end
