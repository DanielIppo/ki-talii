import requests
from datetime import datetime
from typing import Dict, List, Optional, Any


class KimaiClient:
    def __init__(self, base_url: str, token: str, username: Optional[str] = None):
        # Assicura protocollo https e rimuove slash finale
        self.base_url = base_url.rstrip("/")
        if self.base_url.startswith("http://"):
            self.base_url = "https://" + self.base_url[7:]
            
        self.token = token
        self.username = username
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.username:
            self.headers["X-AUTH-USER"] = self.username

    def test_connection(self) -> Dict[str, Any]:
        """Verifica la connessione a Kimai e restituisce le info di versione."""
        url = f"{self.base_url}/version"
        resp = requests.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_customers(self) -> Dict[int, str]:
        """Restituisce mappa {customer_id: customer_name}."""
        url = f"{self.base_url}/customers"
        resp = requests.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return {c["id"]: c["name"] for c in resp.json()}

    def get_projects(self) -> List[Dict[str, Any]]:
        """Restituisce la lista di tutti i progetti disponibili."""
        url = f"{self.base_url}/projects"
        resp = requests.get(url, headers=self.headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_activities(self, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Restituisce le attività (globali o per progetto)."""
        url = f"{self.base_url}/activities"
        params = {}
        if project_id is not None:
            params["project"] = project_id
        resp = requests.get(url, headers=self.headers, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def get_timesheets(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Recupera i timesheet già registrati nell'intervallo specificato."""
        url = f"{self.base_url}/timesheets"
        params = {
            "begin": start_date.strftime("%Y-%m-%dT00:00:00"),
            "end": end_date.strftime("%Y-%m-%dT23:59:59"),
            "size": 150
        }
        resp = requests.get(url, headers=self.headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def create_timesheet(
        self,
        begin: datetime,
        end: datetime,
        project_id: int,
        activity_id: int,
        description: str = "",
        tags: str = "ActivityWatcher"
    ) -> Dict[str, Any]:
        """Crea una nuova voce timesheet su Kimai."""
        url = f"{self.base_url}/timesheets"
        payload = {
            "begin": begin.strftime("%Y-%m-%dT%H:%M:%S"),
            "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
            "project": project_id,
            "activity": activity_id,
            "description": description,
            "tags": tags
        }
        resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
