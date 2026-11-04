import os
import sys

# Assicura corretta codifica UTF-8 su console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml
import argparse
from datetime import datetime, time, timezone, timedelta
from typing import Dict, Any, List

from kimai_client import KimaiClient
from aw_client import ActivityWatcherClient
from merger import EventClassifier, IntervalMerger, ClassifiedEvent, TimesheetBlock
from config_loader import load_config


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def cmd_list_kimai(config: Dict[str, Any]):
    """Stampa l'elenco dei progetti e delle attività disponibili su Kimai."""
    k_conf = config.get("kimai", {})
    client = KimaiClient(k_conf["base_url"], k_conf["token"], k_conf.get("username"))

    print("\n--- PROGETTI DISPONIBILI SU KIMAI ---")
    try:
        customers = client.get_customers()
        projects = client.get_projects()
        activities = client.get_activities()
    except Exception as e:
        print(f"[ERRORE] Impossibile contattare Kimai: {e}")
        return

    # Mappa progetti per cliente
    proj_by_cust = {}
    for p in projects:
        c_id = p.get("customer")
        c_name = customers.get(c_id, f"Cliente #{c_id}")
        proj_by_cust.setdefault(c_name, []).append(p)

    for c_name in sorted(proj_by_cust.keys()):
        print(f"\n[Cliente: {c_name}]")
        for p in sorted(proj_by_cust[c_name], key=lambda x: x["name"]):
            print(f"  • ID {p['id']:<4} -> {p['name']}")

    print("\n--- ATTIVITÀ DISPONIBILI SU KIMAI ---")
    for act in sorted(activities, key=lambda x: x["name"]):
        proj_note = f"(Specifica per Progetto ID {act['project']})" if act.get("project") else "(Globale)"
        print(f"  • ID {act['id']:<4} -> {act['name']:<20} {proj_note}")
    print()


def cmd_aw_raw(config: Dict[str, Any], target_date: datetime.date):
    """Mostra gli eventi finestra grezzi catturati da ActivityWatcher per la data scelta."""
    aw_conf = config.get("activitywatcher", {})
    client = ActivityWatcherClient(aw_conf.get("base_url", "http://localhost:5600/api/0"))

    start_dt = datetime.combine(target_date, time.min).astimezone()
    end_dt = datetime.combine(target_date, time.max).astimezone()

    print(f"\n[ActivityWatcher] Estrazione eventi grezzi per {target_date.strftime('%Y-%m-%d')}...")
    try:
        events = client.query_active_window_events(start_dt, end_dt)
    except Exception as e:
        print(f"[ERRORE] ActivityWatcher: {e}")
        return

    print(f"Trovati {len(events)} eventi attivi (non-AFK).\n")
    print(f"{'Orario':<10} {'Durata':<10} {'App':<25} {'Titolo Finestra'}")
    print("-" * 80)
    for ev in events[-30:]:  # Mostra gli ultimi 30
        ts = datetime.fromisoformat(ev["timestamp"]).astimezone()
        dur = format_duration(ev.get("duration", 0))
        app = ev.get("data", {}).get("app", "")[:23]
        title = ev.get("data", {}).get("title", "")[:45]
        print(f"{ts.strftime('%H:%M:%S'):<10} {dur:<10} {app:<25} {title}")
    print()


def process_day(
    config: Dict[str, Any],
    target_date: datetime.date
) -> tuple[List[TimesheetBlock], List[TimesheetBlock]]:
    """Estrae, classifica e fonde gli eventi del giorno."""
    aw_conf = config.get("activitywatcher", {})
    aw = ActivityWatcherClient(aw_conf.get("base_url", "http://localhost:5600/api/0"))

    start_dt = datetime.combine(target_date, time.min).astimezone()
    end_dt = datetime.combine(target_date, time.max).astimezone()

    raw_events = aw.query_active_window_events(start_dt, end_dt)
    if not raw_events:
        return [], []

    classifier = EventClassifier(config)
    classified_events: List[ClassifiedEvent] = []

    for ev in raw_events:
        ts = datetime.fromisoformat(ev["timestamp"]).astimezone()
        dur = float(ev.get("duration", 0.0))
        data = ev.get("data", {})
        app = data.get("app", "")
        title = data.get("title", "")

        classified = classifier.classify(app, title, ts, dur)
        classified_events.append(classified)

    merger = IntervalMerger(config)
    blocks = merger.merge_events(classified_events)

    matched_blocks = [b for b in blocks if not b.is_unmatched]
    unmatched_blocks = [b for b in blocks if b.is_unmatched]

    return matched_blocks, unmatched_blocks


def print_blocks_table(matched: List[TimesheetBlock], unmatched: List[TimesheetBlock], target_date: datetime.date):
    print(f"\n================================================================================")
    print(f" RIEPILOGO INTERVALLI ORARI - {target_date.strftime('%d/%m/%Y')}")
    print(f"================================================================================")

    if not matched and not unmatched:
        print("Nessuna attività registrata per questa giornata.")
        return

    if matched:
        print(f"\n[✓] BLOCCHI PRONTI PER KIMAI ({len(matched)} intervalli):")
        print(f"{'Inizio - Fine':<17} {'Tempo Lav.':<12} {'Progetto (ID)':<28} {'Attività (ID)':<15}")
        print("-" * 80)
        total_time = 0.0
        for b in matched:
            time_span = f"{b.start.strftime('%H:%M')} - {b.end.strftime('%H:%M')}"
            dur = format_duration(b.active_duration)
            proj_str = f"{b.rule_name} (#{b.project_id})"[:26]
            act_str = f"Attività #{b.activity_id}"
            print(f"{time_span:<17} {dur:<12} {proj_str:<28} {act_str:<15}")
            if b.sample_titles:
                titles_preview = " | ".join(b.sample_titles[:2])
                print(f"   └─ Finestre: {titles_preview[:70]}")
            total_time += b.active_duration
        print("-" * 80)
        print(f"Tempo totale tracciato: {format_duration(total_time)}")

    if unmatched:
        print(f"\n[?] ATTIVITÀ NON RICONOSCIUTE ({len(unmatched)} intervalli):")
        print(f"{'Inizio - Fine':<17} {'Tempo':<12} {'App principali':<25} {'Titoli di esempio'}")
        print("-" * 80)
        for b in unmatched:
            time_span = f"{b.start.strftime('%H:%M')} - {b.end.strftime('%H:%M')}"
            dur = format_duration(b.active_duration)
            apps = ", ".join(list(b.apps)[:2])[:23]
            titles = " | ".join(b.sample_titles[:2])[:35]
            print(f"{time_span:<17} {dur:<12} {apps:<25} {titles}")
        print("\nSuggerimento: puoi mappare queste attività aggiungendo una regola nel file config.yaml")


def sync_to_kimai(
    config: Dict[str, Any],
    blocks: List[TimesheetBlock],
    target_date: datetime.date
):
    if not blocks:
        print("\nNessun blocco associato da inviare a Kimai.")
        return

    k_conf = config.get("kimai", {})
    client = KimaiClient(k_conf["base_url"], k_conf["token"], k_conf.get("username"))
    tag = config.get("settings", {}).get("tag", "ActivityWatcher")

    # Recupera i timesheet già presenti per evitare duplicati
    start_dt = datetime.combine(target_date, time.min)
    end_dt = datetime.combine(target_date, time.max)

    print("\nVerifica timesheet esistenti su Kimai...")
    existing = client.get_timesheets(start_dt, end_dt)

    def is_duplicate(b: TimesheetBlock) -> bool:
        for ex in existing:
            # Se stesso progetto e orario di inizio entro 2 minuti di tolleranza
            ex_begin = datetime.fromisoformat(ex["begin"]).astimezone()
            if ex.get("project") == b.project_id:
                delta = abs((ex_begin - b.start).total_seconds())
                if delta < 120:
                    return True
        return False

    print(f"Invio di {len(blocks)} intervalli a Kimai in corso...")
    inserted = 0
    skipped = 0

    for b in blocks:
        if is_duplicate(b):
            print(f"  [GIA PRESENTE] {b.start.strftime('%H:%M')} - {b.end.strftime('%H:%M')}: {b.rule_name}")
            skipped += 1
            continue

        description = ""
        if b.sample_titles:
            description = "Finestre: " + "; ".join(b.sample_titles[:3])

        try:
            client.create_timesheet(
                begin=b.start,
                end=b.end,
                project_id=b.project_id,
                activity_id=b.activity_id,
                description=description,
                tags=tag
            )
            print(f"  [INVIATO ✓] {b.start.strftime('%H:%M')} - {b.end.strftime('%H:%M')}: {b.rule_name} ({format_duration(b.active_duration)})")
            inserted += 1
        except Exception as e:
            print(f"  [ERRORE X] Fallita creazione per {b.rule_name}: {e}")

    print(f"\nSincronizzazione completata: {inserted} inseriti, {skipped} già presenti.")


def main():
    parser = argparse.ArgumentParser(
        description="Sincronizza le attività reali di ActivityWatcher su Kimai preservando gli intervalli orari."
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Percorso del file di configurazione (default: config.yaml)"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Data da analizzare nel formato YYYY-MM-DD (default: oggi)"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Avvia l'interfaccia grafica interattiva"
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Mostra solo l'anteprima a video senza inviare dati (modalità predefinita)"
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Invia effettivamente i blocchi a Kimai"
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Conferma automatica senza chiedere [y/N] durante il --sync"
    )
    parser.add_argument(
        "--list-kimai",
        action="store_true",
        help="Elenca clienti, progetti e attività presenti su Kimai con i rispettivi ID"
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Mostra gli ultimi eventi finestra catturati da ActivityWatcher per debug"
    )

    args = parser.parse_args()
    config = load_config(args.config)

    # Comando: interfaccia grafica
    if args.gui:
        from gui import ModernAwToKimaiApp
        app = ModernAwToKimaiApp()
        app.mainloop()
        return

    # Comando: elenca ID Kimai
    if args.list_kimai:
        cmd_list_kimai(config)
        return

    # Data target
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now().date()

    # Comando: raw events
    if args.raw:
        cmd_aw_raw(config, target_date)
        return

    # Elaborazione giornata
    matched, unmatched = process_day(config, target_date)
    print_blocks_table(matched, unmatched, target_date)

    # Se richiesto --sync
    if args.sync:
        if not matched:
            return

        if not args.yes:
            resp = input("\nVuoi registrare questi intervalli su Kimai? [y/N]: ").strip().lower()
            if resp not in ["y", "s", "si", "yes"]:
                print("Operazione annullata dall'utente.")
                return

        sync_to_kimai(config, matched, target_date)
    else:
        print("\nModalità Anteprima. Per inviare a Kimai esegui:")
        print("  python sync.py --sync")


if __name__ == "__main__":
    main()
