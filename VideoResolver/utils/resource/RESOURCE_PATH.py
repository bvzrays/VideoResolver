from pathlib import Path

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path("VideoResolver")
CONFIG_PATH = MAIN_PATH / "config.json"
DATA_PATH = MAIN_PATH / "data"
DOWNLOAD_PATH = MAIN_PATH / "downloads"
COOKIE_PATH = MAIN_PATH / "cookies"
TEMPLATES_PATH = MAIN_PATH / "templates"
ASSET_PATH = Path(__file__).resolve().parents[2] / "assets"

for path in (MAIN_PATH, DATA_PATH, DOWNLOAD_PATH, COOKIE_PATH, TEMPLATES_PATH):
    path.mkdir(parents=True, exist_ok=True)
