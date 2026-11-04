import os
import re
import yaml
from typing import Dict, Any, Optional


def load_env_file(dotenv_path: Optional[str] = None):
    """Carica variabili d'ambiente da file .env senza dipendenze esterne."""
    if dotenv_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        dotenv_path = os.path.join(base_dir, ".env")

    if not os.path.exists(dotenv_path):
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception as e:
        print(f"[AVVISO] Impossibile leggere il file .env: {e}")


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
    Carica la configurazione unendo le variabili da .env e da config.yaml (o config.example.yaml).
    Garantisce che credenziali e URL vengano presi prioritariamente dal file .env.
    """
    # 1. Carica le variabili da .env
    load_env_file()

    # 2. Risolvi il percorso del file yaml
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if not config_path:
        local_config = os.path.join(base_dir, "config.yaml")
        example_config = os.path.join(base_dir, "config.example.yaml")
        if os.path.exists(local_config):
            config_path = local_config
        elif os.path.exists(example_config):
            config_path = example_config
        else:
            config_path = "config.yaml"
    elif not os.path.isabs(config_path):
        candidate = os.path.join(base_dir, config_path)
        if os.path.exists(candidate):
            config_path = candidate

    config: Dict[str, Any] = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
            config = _substitute_env_vars(raw)

    # 3. Override diretto da variabili d'ambiente per massima sicurezza
    if "kimai" not in config:
        config["kimai"] = {}

    if os.environ.get("KIMAI_BASE_URL"):
        config["kimai"]["base_url"] = os.environ["KIMAI_BASE_URL"]
    if os.environ.get("KIMAI_TOKEN"):
        config["kimai"]["token"] = os.environ["KIMAI_TOKEN"]
    if os.environ.get("KIMAI_USERNAME"):
        config["kimai"]["username"] = os.environ["KIMAI_USERNAME"]

    if "activitywatcher" not in config:
        config["activitywatcher"] = {}
    if os.environ.get("ACTIVITYWATCHER_BASE_URL"):
        config["activitywatcher"]["base_url"] = os.environ["ACTIVITYWATCHER_BASE_URL"]

    return config
