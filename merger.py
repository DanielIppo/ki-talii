import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field


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


class IntervalMerger:
    def __init__(self, config: Dict[str, Any]):
        settings = config.get("settings", {})
        self.max_gap_seconds = settings.get("max_gap_seconds", 300)  # Micro-pause tollerate (5 minuti)
        self.max_merge_gap_seconds = settings.get("max_merge_gap_seconds", 1800)  # Max pausa tra blocchi stesso progetto (30 min)
        self.min_duration_seconds = settings.get("min_duration_seconds", 120)  # Minimo 2 minuti di lavoro

    def merge_events(self, events: List[ClassifiedEvent]) -> List[TimesheetBlock]:
        """
        Raggruppa gli eventi sequenziali in blocchi orari reali,
        fondendo micro-passaggi tra finestre dello stesso progetto
        e interrompendo i blocchi solo su cambi effettivi di progetto o lunghe pause.
        """
        if not events:
            return []

        blocks: List[TimesheetBlock] = []
        current_block: Optional[TimesheetBlock] = None

        i = 0
        n = len(events)

        while i < n:
            ev = events[i]

            # Se l'evento è ignorato (es. WhatsApp, blocco schermo)
            if ev.status == "ignored":
                # Controlla se è una distrazione momentanea durante un blocco in corso
                if current_block and not current_block.is_unmatched:
                    # Cerca in avanti se l'utente ritorna allo stesso progetto a breve
                    next_matched = self._find_next_matched(events, i + 1, self.max_gap_seconds, current_block.end)
                    if next_matched and next_matched.project_id == current_block.project_id:
                        # Breve pausa/distrazione tollerata: non chiudiamo il blocco principale
                        i += 1
                        continue
                    else:
                        # Il lavoro sul blocco corrente si è interrotto
                        blocks.append(current_block)
                        current_block = None
                i += 1
                continue

            # Evento con Match su Progetto
            if ev.status == "matched":
                if current_block is None:
                    # Inizia un nuovo blocco
                    current_block = TimesheetBlock(
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
                    # C'è già un blocco attivo
                    if (current_block.project_id == ev.project_id and 
                        current_block.activity_id == ev.activity_id and
                        not current_block.is_unmatched):
                        
                        gap = (ev.start - current_block.end).total_seconds()
                        if gap <= self.max_gap_seconds:
                            # Estende il blocco corrente
                            current_block.end = max(current_block.end, ev.end)
                            current_block.active_duration += ev.duration
                            if ev.app:
                                current_block.apps.add(ev.app)
                            if ev.title and ev.title not in current_block.sample_titles and len(current_block.sample_titles) < 5:
                                current_block.sample_titles.append(ev.title)
                        else:
                            # Pausa troppo lunga: chiudi il blocco precedente e aprine uno nuovo
                            blocks.append(current_block)
                            current_block = TimesheetBlock(
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
                        # Cambio progetto: chiudi il vecchio blocco
                        blocks.append(current_block)
                        current_block = TimesheetBlock(
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

            # Evento Unmatched (non riconosciuto)
            elif ev.status == "unmatched":
                if current_block and not current_block.is_unmatched:
                    # Verifichiamo se è una breve consultazione (es. browser generico o DBeaver)
                    # prima di ritornare allo stesso progetto
                    next_matched = self._find_next_matched(events, i + 1, self.max_gap_seconds, current_block.end)
                    if next_matched and next_matched.project_id == current_block.project_id:
                        # Fa parte del contesto del progetto in corso
                        current_block.end = max(current_block.end, ev.end)
                        current_block.active_duration += ev.duration
                        if ev.app:
                            current_block.apps.add(ev.app)
                        i += 1
                        continue
                    else:
                        # Chiusura del blocco di progetto
                        blocks.append(current_block)
                        current_block = None

                # Creazione/estensione blocco unmatched
                if current_block is None:
                    current_block = TimesheetBlock(
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
                    gap = (ev.start - current_block.end).total_seconds()
                    if gap <= self.max_gap_seconds:
                        current_block.end = max(current_block.end, ev.end)
                        current_block.active_duration += ev.duration
                        if ev.app:
                            current_block.apps.add(ev.app)
                        if ev.title and ev.title not in current_block.sample_titles and len(current_block.sample_titles) < 5:
                            current_block.sample_titles.append(ev.title)
                    else:
                        blocks.append(current_block)
                        current_block = TimesheetBlock(
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

            i += 1

        if current_block:
            blocks.append(current_block)

        # 1. Filtra blocchi brevissimi (sotto la soglia minima di secondi)
        filtered_blocks = [
            b for b in blocks if b.active_duration >= self.min_duration_seconds
        ]

        # 2. Consolidamento blocchi dello stesso progetto:
        # Se non ci sono altri progetti intermedi e la pausa è sotto max_merge_gap_seconds,
        # fonde i blocchi in un unico intervallo continuo.
        return self._consolidate_blocks(filtered_blocks)

    def _consolidate_blocks(self, blocks: List[TimesheetBlock]) -> List[TimesheetBlock]:
        if not blocks:
            return []

        consolidated: List[TimesheetBlock] = []
        curr = blocks[0]

        for nxt in blocks[1:]:
            # Se entrambi sono matched e appartengono allo stesso progetto e attività
            if (not curr.is_unmatched and not nxt.is_unmatched and
                curr.project_id == nxt.project_id and
                curr.activity_id == nxt.activity_id):
                
                gap = (nxt.start - curr.end).total_seconds()
                if gap <= self.max_merge_gap_seconds:
                    # Fonde nxt nel blocco curr
                    curr.end = max(curr.end, nxt.end)
                    curr.active_duration += nxt.active_duration
                    curr.apps.update(nxt.apps)
                    for t in nxt.sample_titles:
                        if t not in curr.sample_titles and len(curr.sample_titles) < 6:
                            curr.sample_titles.append(t)
                    continue

            # Se entrambi sono unmatched contigui entro la pausa
            elif curr.is_unmatched and nxt.is_unmatched:
                gap = (nxt.start - curr.end).total_seconds()
                if gap <= self.max_merge_gap_seconds:
                    curr.end = max(curr.end, nxt.end)
                    curr.active_duration += nxt.active_duration
                    curr.apps.update(nxt.apps)
                    for t in nxt.sample_titles:
                        if t not in curr.sample_titles and len(curr.sample_titles) < 6:
                            curr.sample_titles.append(t)
                    continue

            consolidated.append(curr)
            curr = nxt

        consolidated.append(curr)
        return consolidated

    def _find_next_matched(
        self,
        events: List[ClassifiedEvent],
        start_index: int,
        max_gap_seconds: float,
        last_end: datetime
    ) -> Optional[ClassifiedEvent]:
        """Cerca il prossimo evento 'matched' entro un intervallo di tempo ragionevole."""
        for j in range(start_index, len(events)):
            ev = events[j]
            gap = (ev.start - last_end).total_seconds()
            if gap > max_gap_seconds:
                return None
            if ev.status == "matched":
                return ev
        return None
