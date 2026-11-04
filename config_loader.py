import os
import re
import yaml
from typing import Dict, Any, Optional
from settings_manager import load_settings


def _substitute_env_vars(obj: Any) -> Any:
    """Sostituisce ricorsivamente le variabili ${VAR_NAME} con il valore da os.environ."""
    pattern = re.compile(r"\$\{([A-Za-z0-9_]+)\}")

    if isinstance(obj, str):
        def replace_match(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))
        return pattern.sub(replace_match, obj)
    elif isinstance(obj, dict):
        return {k: _substitute_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute_env_vars(elem) for elem in obj]
    return obj


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Carica la configurazione combinando le impostazioni utente (settings.json / .env)
    con il file delle regole YAML specificato o predefinito.
    """
    settings = load_settings()

    # Se non è passato un config_path esplicito, usa quello registrato nei settings
    if not config_path:
        config_path = settings.get("rules_file")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    if not config_path or not os.path.exists(config_path):
        local_config = os.path.join(base_dir, "config.yaml")
        example_config = os.path.join(base_dir, "config.example.yaml")
        if os.path.exists(local_config):
            config_path = local_config
        elif os.path.exists(example_config):
            config_path = example_config

    config: Dict[str, Any] = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
                config = _substitute_env_vars(raw)
        except Exception as e:
            print(f"[ERRORE] Impossibile leggere il file regole '{config_path}': {e}")

    # Applica i parametri Kimai e AW dalle impostazioni
    if "kimai" not in config:
        config["kimai"] = {}
    config["kimai"]["base_url"] = settings.get("kimai_url", "")
    config["kimai"]["token"] = settings.get("kimai_token", "")
    config["kimai"]["username"] = settings.get("kimai_username", "")

    if "activitywatcher" not in config:
        config["activitywatcher"] = {}
    config["activitywatcher"]["base_url"] = settings.get("aw_url", "http://localhost:5600/api/0")

    return config
