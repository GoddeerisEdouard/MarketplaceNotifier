import configparser
import os
from pathlib import Path

def load_config():
    config = configparser.ConfigParser()
    config_dir = Path(__file__).parent
    config.read(config_dir / "config.ini")
    env = "docker" if os.getenv('USE_DOCKER_CONFIG', 'false').lower() == 'true' else "local"
    config_dict = {
        "webserver_host": config[env]["webserver_host"],
        "redis_host": config[env]["redis_host"],
        "database_path": None
    }

    if env == "local":
        resolved_path = os.path.abspath(config_dir / config[env]["database_path"])
        config_dict["database_path"] = resolved_path
    elif env == "docker":
        config_dict["database_path"] = config[env]["database_path"]
    config_dict["default_db_url"] = f"sqlite://{config_dict['database_path']}/db.sqlite3"

    return config_dict


config = load_config()
