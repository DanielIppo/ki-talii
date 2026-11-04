import requests
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional


class ActivityWatcherClient:
    def __init__(self, base_url: str = "http://localhost:5600/api/0"):
        self.base_url = base_url.rstrip("/")

    def test_connection(self) -> Dict[str, Any]:
        """Verifica se il server locale di ActivityWatcher è attivo."""
        url = f"{self.base_url}/info"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_buckets(self) -> Dict[str, Any]:
        """Ottiene l'elenco dei bucket registrati."""
        url = f"{self.base_url}/buckets/"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return resp.json()

    def get_window_and_afk_buckets(self) -> tuple[Optional[str], Optional[str]]:
        """Rileva automaticamente i nomi dei bucket per finestre e AFK."""
        buckets = self.get_buckets()
        window_bucket = None
        afk_bucket = None

        for b_name in buckets.keys():
            if b_name.startswith("aw-watcher-window_") and not window_bucket:
                window_bucket = b_name
            elif b_name.startswith("aw-watcher-afk_") and not afk_bucket:
                afk_bucket = b_name

        return window_bucket, afk_bucket

    def query_active_window_events(
        self,
        start_dt: datetime,
        end_dt: datetime
    ) -> List[Dict[str, Any]]:
        """
        Interroga ActivityWatcher usando la query canonica flood() e filter_period_intersect(),
        in modo da considerare ESCLUSIVAMENTE gli eventi finestra durante i periodi 'not-afk'.
        """
        window_bucket, afk_bucket = self.get_window_and_afk_buckets()
        if not window_bucket or not afk_bucket:
            raise RuntimeError(
                f"Bucket non trovati su ActivityWatcher. Window: {window_bucket}, AFK: {afk_bucket}"
            )

        # Assicura formato ISO UTC per timeperiod
        start_iso = start_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = end_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        timeperiod = f"{start_iso}/{end_iso}"

        query = [
            f'window_events = flood(query_bucket("{window_bucket}"));',
            f'afk_events = flood(query_bucket("{afk_bucket}"));',
            'not_afk_events = filter_keyvals(afk_events, "status", ["not-afk"]);',
            'active_window_events = filter_period_intersect(window_events, not_afk_events);',
            'RETURN = active_window_events;'
        ]

        payload = {
            "query": query,
            "timeperiods": [timeperiod]
        }

        url = f"{self.base_url}/query/"
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        # data è una lista di risultati (uno per ogni timeperiod specificato)
        if isinstance(data, list) and len(data) > 0:
            events = data[0]
            # Ordina cronologicamente
            events.sort(key=lambda ev: ev.get("timestamp", ""))
            return events
        return []
