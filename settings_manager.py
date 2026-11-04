import os
import sys
import json
import yaml
import platform
import webbrowser
from typing import Dict, Any, Optional

from kimai_client import KimaiClient
from aw_client import ActivityWatcherClient


def get_app_data_dir() -> str:
    """Restituisce la cartella standard dei dati applicazione per il sistema operativo corrente."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        app_dir = os.path.join(base, "ki-talii")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        app_dir = os.path.join(base, "ki-talii")

    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def get_settings_file_path() -> str:
    return os.path.join(get_app_data_dir(), "settings.json")


def load_settings() -> Dict[str, Any]:
    """
    Carica le impostazioni salvate nell'AppData o fallback su .env / locale.
    """
    settings_file = get_settings_file_path()
    local_dir = os.path.dirname(os.path.abspath(__file__))
    local_env = os.path.join(local_dir, ".env")
    local_rules = os.path.join(local_dir, "config.yaml")

    defaults = {
        "kimai_url": "",
        "kimai_username": "",
        "kimai_token": "",
        "aw_url": "http://localhost:5600/api/0",
        "rules_file": "",
        "theme": "dark"
    }

    # Carica da .env se presente come fallback
    if os.path.exists(local_env):
        try:
            with open(local_env, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k == "KIMAI_BASE_URL":
                            defaults["kimai_url"] = v
                        elif k == "KIMAI_TOKEN":
                            defaults["kimai_token"] = v
                        elif k == "KIMAI_USERNAME":
                            defaults["kimai_username"] = v
                        elif k == "ACTIVITYWATCHER_BASE_URL":
                            defaults["aw_url"] = v
        except Exception:
            pass

    # Se esiste il file settings.json utente, carica quello
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception as e:
            print(f"[AVVISO] Errore lettura {settings_file}: {e}")

    # Se il rules_file non è impostato, cerca config.yaml nella cartella locale
    if not defaults.get("rules_file") or not os.path.exists(defaults["rules_file"]):
        if os.path.exists(local_rules):
            defaults["rules_file"] = local_rules
        else:
            defaults["rules_file"] = os.path.join(local_dir, "config.example.yaml")

    return defaults


def save_settings(settings: Dict[str, Any]):
    """Salva le impostazioni nel file JSON persistente dell'utente."""
    settings_file = get_settings_file_path()
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)


def check_activitywatcher_online(base_url: str = "http://localhost:5600/api/0") -> bool:
    """Verifica se ActivityWatcher è in esecuzione."""
    client = ActivityWatcherClient(base_url)
    try:
        client.test_connection()
        return True
    except Exception:
        return False


def open_activitywatcher_download_page():
    """Apre la pagina ufficiale di download di ActivityWatcher."""
    webbrowser.open("https://activitywatch.net/downloads/")


def export_kimai_projects_to_file(
    kimai_url: str,
    kimai_token: str,
    kimai_username: Optional[str],
    output_path: str
) -> int:
    """
    Interroga Kimai e genera un file di testo formattato con tutti i clienti,
    progetti e attività, pronto da consultare per scrivere le regole YAML.
    Restituisce il numero totale di progetti trovati.
    """
    client = KimaiClient(base_url=kimai_url, token=kimai_token, username=kimai_username)
    customers = client.get_customers()
    projects = client.get_projects()
    activities = client.get_activities()

    # Raggruppa per cliente
    proj_by_cust = {}
    for p in projects:
        c_id = p.get("customer")
        c_name = customers.get(c_id, f"Cliente #{c_id}")
        proj_by_cust.setdefault(c_name, []).append(p)

    lines = []
    lines.append("=" * 80)
    lines.append(" ELENCO PROGETTI E ATTIVITÀ DISPONIBILI SU KIMAI")
    lines.append(f" Generato da ki-talii il: {os.path.basename(output_path)}")
    lines.append("=" * 80)
    lines.append("")
    lines.append("Usa questi ID nel tuo file di regole (config.yaml) per associare le finestre.")
    lines.append("")

    lines.append("--- PROGETTI SUDDIVISI PER CLIENTE ---")
    for c_name in sorted(proj_by_cust.keys()):
        lines.append(f"\n[Cliente: {c_name}]")
        for p in sorted(proj_by_cust[c_name], key=lambda x: x["name"]):
            lines.append(f"  • ID {p['id']:<4} -> {p['name']}")

    lines.append("\n" + "-" * 80)
    lines.append("--- ATTIVITÀ DISPONIBILI ---")
    for act in sorted(activities, key=lambda x: x["name"]):
        proj_note = f"(Specifica per Progetto ID {act['project']})" if act.get("project") else "(Globale)"
        lines.append(f"  • ID {act['id']:<4} -> {act['name']:<25} {proj_note}")

    lines.append("\n" + "=" * 80)
    lines.append("ESEMPIO DI REGOLA DA COPIARE IN config.yaml:")
    lines.append("""
rules:
  - name: "Nome Progetto"
    project_id: <ID_PROGETTO>
    activity_id: <ID_ATTIVITA>   # es. 18 per Sviluppo, 19 per Assistenza
    patterns:
      - "(?i)parola_chiave_titolo_finestra"
""")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return len(projects)
