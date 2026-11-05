import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from copy import deepcopy


@dataclass
class ClassifiedEvent:
    start: datetime
    end: datetime
    duration: float
    app: str
    title: str
    status: str  # "matched", "ignored", "unmatched"
    project_id: Optional[int] = None
    activity_id: Optional[int] = None
    rule_name: Optional[str] = None


@dataclass
class TimesheetBlock:
    project_id: Optional[int]
    activity_id: Optional[int]
    rule_name: str
    start: datetime
    end: datetime
    active_duration: float  # Secondi totali di attività effettiva
    apps: Set[str] = field(default_factory=set)
    sample_titles: List[str] = field(default_factory=list)
    is_unmatched: bool = False

    @property
    def total_span_seconds(self) -> float:
        """Differenza tra orario fine e orario inizio."""
        return (self.end - self.start).total_seconds()


class EventClassifier:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.default_activity_id = config.get("settings", {}).get("default_activity_id", 18)
        self.ignored_apps = [a.lower() for a in config.get("ignored_apps", [])]
        self.ignored_patterns = [
            re.compile(p, re.IGNORECASE) for p in config.get("ignored_patterns", [])
        ]
        self.rules = config.get("rules", [])
        self._compiled_rules = []

        for r in self.rules:
            patterns = [re.compile(p, re.IGNORECASE) for p in r.get("patterns", [])]
            apps = [a.lower() for a in r.get("apps", [])]
            self._compiled_rules.append({
                "name": r.get("name", f"Progetto #{r.get('project_id')}"),
                "project_id": r.get("project_id"),
                "activity_id": r.get("activity_id", self.default_activity_id),
                "patterns": patterns,
                "apps": apps
            })

    def classify(self, app: str, title: str, start: datetime, duration: float) -> ClassifiedEvent:
        end = start + timedelta(seconds=duration)
        app_clean = (app or "").strip()
        title_clean = (title or "").strip()
        app_lower = app_clean.lower()

        # 1. Verifica app ignorate
        if app_lower in self.ignored_apps:
            return ClassifiedEvent(start, end, duration, app_clean, title_clean, status="ignored")

        # 2. Verifica pattern titolo ignorati
        for pattern in self.ignored_patterns:
            if pattern.search(title_clean):
                return ClassifiedEvent(start, end, duration, app_clean, title_clean, status="ignored")

        # 3. Verifica regole di progetto
        for rule in self._compiled_rules:
            # Se la regola specifica app dedicate, deve corrispondere
            if rule["apps"] and app_lower not in rule["apps"]:
                continue

            # Verifica corrispondenza su pattern (titolo o nome app)
            matched = False
            for pat in rule["patterns"]:
                if pat.search(title_clean) or pat.search(app_clean):
                    matched = True
                    break

            # Se la regola ha solo app senza pattern, corrisponde all'app
            if not rule["patterns"] and rule["apps"] and app_lower in rule["apps"]:
                matched = True

            if matched:
                return ClassifiedEvent(
                    start=start,
                    end=end,
                    duration=duration,
                    app=app_clean,
                    title=title_clean,
                    status="matched",
                    project_id=rule["project_id"],
                    activity_id=rule["activity_id"],
                    rule_name=rule["name"]
                )

        # 4. Nessuna regola trovata
        return ClassifiedEvent(start, end, duration, app_clean, title_clean, status="unmatched")


NEUTRAL_DEV_APPS = {
    "dbeaver.exe", "soffice.bin", "excel.exe", "postman.exe", "insomnia.exe",
    "docker desktop.exe", "lens.exe"
}


def is_neutral_developer_tool(app: str, title: str) -> bool:
    app_lower = app.lower()
    title_lower = title.lower()
    if app_lower in NEUTRAL_DEV_APPS:
        return True
    if any(k in title_lower for k in ["swagger", "devtools", "keycloak"]):
        return True
    return False


class IntervalMerger:
    def __init__(self, config: Dict[str, Any]):
        settings = config.get("settings", {})
        self.max_gap_seconds = settings.get("max_gap_seconds", 300)  # Micro-pause tollerate (5 minuti)
        self.max_merge_gap_seconds = settings.get("max_merge_gap_seconds", 1200)  # Max pausa tra blocchi stesso progetto (20 min)
        self.min_duration_seconds = settings.get("min_duration_seconds", 120)  # Minimo 2 minuti di lavoro
        self.blip_threshold_seconds = 25  # Soglia sotto la quale un blocco è un micro-click isolato e non estende sessioni oltre i 5 min

    def _apply_context_inheritance(self, events: List[ClassifiedEvent]) -> List[ClassifiedEvent]:
        """
        Tool di sviluppo neutri (DBeaver, Calc, DevTools, Swagger, Lens) usati durante lo sviluppo
        ereditano automaticamente il progetto dominante nella finestra temporale precedente (15 min),
        evitando di ereditare click accidentali o schede secondarie.
        """
        result: List[ClassifiedEvent] = []
        for ev in events:
            ev_c = deepcopy(ev)
            if ev_c.status == "unmatched" and is_neutral_developer_tool(ev_c.app, ev_c.title):
                project_durations: Dict[Tuple[int, int, str], float] = {}
                project_last: Dict[Tuple[int, int, str], ClassifiedEvent] = {}
                for p in reversed(result):
                    gap = (ev_c.start - p.end).total_seconds()
                    if gap > 900:  # Finestra di 15 minuti
                        break
                    if p.status == "matched":
                        key = (p.project_id, p.activity_id, p.rule_name)
                        project_durations[key] = project_durations.get(key, 0.0) + p.duration
                        if key not in project_last:
                            project_last[key] = p

                if project_durations:
                    best_key = max(project_durations.keys(), key=lambda k: project_durations[k])
                    if project_durations[best_key] >= self.blip_threshold_seconds:
                        best_p = project_last[best_key]
                        ev_c.status = "matched"
                        ev_c.project_id = best_p.project_id
                        ev_c.activity_id = best_p.activity_id
                        ev_c.rule_name = best_p.rule_name
            result.append(ev_c)
        return result

    def _smooth_fleeting_noise(self, events: List[ClassifiedEvent]) -> List[ClassifiedEvent]:
        """
        Filtra schede in background o click accidentali (< 15 secondi) di un altro progetto
        quando ci si trova all'interno di una sessione continua di un unico progetto.
        """
        smoothed: List[ClassifiedEvent] = []
        n = len(events)
        for i, ev in enumerate(events):
            ev_c = deepcopy(ev)
            if ev_c.status == "matched" and ev_c.duration < 15:
                prev_p = None
                for p in reversed(smoothed):
                    if p.status == "matched":
                        prev_p = p
                        break
                next_p = None
                for j in range(i + 1, min(i + 10, n)):
                    if events[j].status == "matched":
                        next_p = events[j]
                        break
                if (prev_p and next_p and 
                    prev_p.project_id == next_p.project_id and 
                    prev_p.project_id != ev_c.project_id and
                    prev_p.activity_id != 4):
                    # Click fugace nel mezzo di una sessione coerente
                    ev_c.project_id = prev_p.project_id
                    ev_c.activity_id = prev_p.activity_id
                    ev_c.rule_name = prev_p.rule_name
            smoothed.append(ev_c)
        return smoothed

    def _apply_meeting_continuation(self, events: List[ClassifiedEvent]) -> List[ClassifiedEvent]:
        """
        Assicura che durante una call (Google Meet, Teams, Zoom) gli eventi correlati
        entro 10 minuti mantengano l'attività 'Call' e il progetto della chiamata.
        """
        in_call_project = None
        last_call_time = None
        for ev in events:
            is_call = ev.activity_id == 4 or "meet" in ev.title.lower() or "teams" in ev.title.lower() or "zoom" in ev.title.lower()
            if is_call and ev.status == "matched":
                in_call_project = (ev.project_id, ev.rule_name)
                last_call_time = ev.end
            elif in_call_project and last_call_time:
                gap = (ev.start - last_call_time).total_seconds()
                if gap <= 600:
                    if any(k in ev.title.lower() for k in ["meet", "google meet", "teams", "zoom"]):
                        ev.status = "matched"
                        ev.project_id = in_call_project[0]
                        ev.activity_id = 4
                        ev.rule_name = in_call_project[1]
                        last_call_time = ev.end
                else:
                    in_call_project = None
        return events

    def merge_events(self, events: List[ClassifiedEvent]) -> List[TimesheetBlock]:
        """
        Raggruppa gli eventi sequenziali in blocchi orari reali,
        applicando Context Inheritance, Noise Smoothing e consolidamento
        con supporto alle attività parallele (Opzione B).
        """
        if not events:
            return []

        # 1. Applicazione filtri intelligenti e context inheritance
        events_step1 = self._apply_context_inheritance(events)
        events_step2 = self._smooth_fleeting_noise(events_step1)
        cleaned_events = self._apply_meeting_continuation(events_step2)

        # 2. Aggregazione sequenziale in raw blocks
        blocks: List[TimesheetBlock] = []
        curr: Optional[TimesheetBlock] = None

        for ev in cleaned_events:
            if ev.status == "ignored":
                continue

            if ev.status == "matched":
                if curr is None:
                    curr = TimesheetBlock(
                        project_id=ev.project_id,
                        activity_id=ev.activity_id,
                        rule_name=ev.rule_name or f"Progetto #{ev.project_id}",
                        start=ev.start,
                        end=ev.end,
                        active_duration=ev.duration,
                        apps={ev.app} if ev.app else set(),
                        sample_titles=[ev.title] if ev.title else [],
                        is_unmatched=False
                    )
                else:
                    if (not curr.is_unmatched and 
                        curr.project_id == ev.project_id and 
                        curr.activity_id == ev.activity_id):
                        
                        gap = (ev.start - curr.end).total_seconds()
                        if gap <= self.max_gap_seconds:
                            curr.end = max(curr.end, ev.end)
                            curr.active_duration += ev.duration
                            if ev.app:
                                curr.apps.add(ev.app)
                            if ev.title and ev.title not in curr.sample_titles and len(curr.sample_titles) < 6:
                                curr.sample_titles.append(ev.title)
                        else:
                            blocks.append(curr)
                            curr = TimesheetBlock(
                                project_id=ev.project_id,
                                activity_id=ev.activity_id,
                                rule_name=ev.rule_name or f"Progetto #{ev.project_id}",
                                start=ev.start,
                                end=ev.end,
                                active_duration=ev.duration,
                                apps={ev.app} if ev.app else set(),
                                sample_titles=[ev.title] if ev.title else [],
                                is_unmatched=False
                            )
                    else:
                        blocks.append(curr)
                        curr = TimesheetBlock(
                            project_id=ev.project_id,
                            activity_id=ev.activity_id,
                            rule_name=ev.rule_name or f"Progetto #{ev.project_id}",
                            start=ev.start,
                            end=ev.end,
                            active_duration=ev.duration,
                            apps={ev.app} if ev.app else set(),
                            sample_titles=[ev.title] if ev.title else [],
                            is_unmatched=False
                        )
            elif ev.status == "unmatched":
                if curr and not curr.is_unmatched:
                    blocks.append(curr)
                    curr = None

                if curr is None:
                    curr = TimesheetBlock(
                        project_id=None,
                        activity_id=None,
                        rule_name="[NON RICONOSCIUTO]",
                        start=ev.start,
                        end=ev.end,
                        active_duration=ev.duration,
                        apps={ev.app} if ev.app else set(),
                        sample_titles=[ev.title] if ev.title else [],
                        is_unmatched=True
                    )
                else:
                    gap = (ev.start - curr.end).total_seconds()
                    if gap <= self.max_gap_seconds:
                        curr.end = max(curr.end, ev.end)
                        curr.active_duration += ev.duration
                        if ev.app:
                            curr.apps.add(ev.app)
                        if ev.title and ev.title not in curr.sample_titles and len(curr.sample_titles) < 6:
                            curr.sample_titles.append(ev.title)
                    else:
                        blocks.append(curr)
                        curr = TimesheetBlock(
                            project_id=None,
                            activity_id=None,
                            rule_name="[NON RICONOSCIUTO]",
                            start=ev.start,
                            end=ev.end,
                            active_duration=ev.duration,
                            apps={ev.app} if ev.app else set(),
                            sample_titles=[ev.title] if ev.title else [],
                            is_unmatched=True
                        )

        if curr:
            blocks.append(curr)

        # 3. Consolidamento avanzato dei blocchi dello stesso progetto (Opzione B: Record Paralleli)
        consolidated = self._consolidate_blocks(blocks)

        # 4. Filtro finale per durata minima
        return [
            b for b in consolidated 
            if b.active_duration >= self.min_duration_seconds or (b.activity_id == 4 and b.total_span_seconds >= 300)
        ]

    def _consolidate_blocks(self, blocks: List[TimesheetBlock]) -> List[TimesheetBlock]:
        """
        Fonde blocchi dello stesso progetto entro max_merge_gap_seconds (20 min).
        Supporta la registrazione parallela (Opzione B) senza che progetti concorrenti
        spezzino sessioni continue.
        Include protezione anti-micro-blip: blocchi con attività inferiore a blip_threshold_seconds (< 25s)
        non possono fungere da ponte né estendere sessioni attraverso pause > 5 minuti.
        """
        if not blocks:
            return []

        consolidated: List[TimesheetBlock] = []
        i = 0

        while i < len(blocks):
            b = blocks[i]
            if b.is_unmatched:
                consolidated.append(b)
                i += 1
                continue

            j = i + 1
            while j < len(blocks):
                nxt = blocks[j]
                gap = (nxt.start - b.end).total_seconds()
                if gap > self.max_merge_gap_seconds:
                    break

                # Opzione B (Record Paralleli):
                # Se nxt appartiene a un altro progetto o non è riconosciuto,
                # continuiamo a scorrere per trovare blocchi dello stesso progetto senza spezzarlo.
                if nxt.is_unmatched or nxt.project_id != b.project_id:
                    j += 1
                    continue

                # Se troviamo un blocco dello stesso progetto e attività
                if nxt.project_id == b.project_id and nxt.activity_id == b.activity_id:
                    # Protezione Anti-Micro-Blip:
                    # 1. Se il blocco 'b' ha lavorato meno della soglia e il gap è > 5 minuti,
                    # è un click isolato e non può estendersi su una sessione futura.
                    if gap > 300 and b.active_duration < self.blip_threshold_seconds:
                        break
                    # 2. Se 'nxt' ha lavorato meno della soglia e il gap è > 5 minuti,
                    # è un click isolato e non deve tirare indietro o allungare la sessione.
                    if gap > 300 and nxt.active_duration < self.blip_threshold_seconds:
                        j += 1
                        continue

                    b.end = max(b.end, nxt.end)
                    b.active_duration += nxt.active_duration
                    b.apps.update(nxt.apps)
                    for t in nxt.sample_titles:
                        if t not in b.sample_titles and len(b.sample_titles) < 6:
                            b.sample_titles.append(t)
                    blocks.pop(j)
                    continue
                break

            consolidated.append(b)
            i += 1

        return consolidated
