import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml
import calendar
import threading
import queue
from datetime import datetime, date, timedelta, time
from typing import Dict, Any, List, Optional
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image

from kimai_client import KimaiClient
from aw_client import ActivityWatcherClient
from merger import EventClassifier, IntervalMerger, ClassifiedEvent, TimesheetBlock
from config_loader import load_config
from settings_manager import (
    load_settings,
    save_settings,
    check_activitywatcher_online,
    open_activitywatcher_download_page,
    export_kimai_projects_to_file
)

APP_VERSION = "1.1"


def get_resource_path(relative_path: str) -> str:
    """
    Restituisce il percorso assoluto di una risorsa, compatibile con PyInstaller e dev locale.
    """
    if getattr(sys, 'frozen', False):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    path = os.path.join(base_dir, relative_path)
    if os.path.exists(path):
        return path

    alt_path = os.path.join(os.path.dirname(sys.executable), relative_path)
    if os.path.exists(alt_path):
        return alt_path
    return path


def format_duration(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


class ModernCalendarDialog(ctk.CTkToplevel):
    """Mini calendario popup in CustomTkinter."""
    def __init__(self, parent, current_date: date, on_select):
        super().__init__(parent)
        self.title("Seleziona data")
        self.geometry("340x360")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_select = on_select
        self.year = current_date.year
        self.month = current_date.month
        self.selected_date = current_date

        self._build_ui()

    def _build_ui(self):
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(fill="x", padx=15, pady=(15, 10))

        btn_prev = ctk.CTkButton(nav_frame, text="◀", width=35, height=30, command=self._prev_month)
        btn_prev.pack(side="left")

        self.lbl_month_year = ctk.CTkLabel(nav_frame, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self.lbl_month_year.pack(side="left", expand=True)

        btn_next = ctk.CTkButton(nav_frame, text="▶", width=35, height=30, command=self._next_month)
        btn_next.pack(side="right")

        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.pack(padx=15, pady=5)

        self._render_days()

    def _render_days(self):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        month_names = [
            "", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
        ]
        self.lbl_month_year.configure(text=f"{month_names[self.month]} {self.year}")

        days_header = ["Lu", "Ma", "Me", "Gi", "Ve", "Sa", "Do"]
        for col, h in enumerate(days_header):
            lbl = ctk.CTkLabel(
                self.grid_frame,
                text=h,
                width=38,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray30", "gray70")
            )
            lbl.grid(row=0, column=col, pady=2)

        cal = calendar.Calendar(firstweekday=0)
        month_days = cal.monthdayscalendar(self.year, self.month)
        today = date.today()

        for r_idx, week in enumerate(month_days):
            for c_idx, day in enumerate(week):
                if day == 0:
                    continue
                d_obj = date(self.year, self.month, day)
                is_selected = (d_obj == self.selected_date)
                is_today = (d_obj == today)

                btn_color = ("#1f538d", "#1f538d") if is_selected else ("#e1e9f5", "#2a2d32")
                text_color = "white" if is_selected else ("#1a73e8" if is_today else ("gray10", "gray90"))

                btn = ctk.CTkButton(
                    self.grid_frame,
                    text=str(day),
                    width=38,
                    height=32,
                    corner_radius=6,
                    fg_color=btn_color,
                    text_color=text_color,
                    hover_color=("#1668c1", "#3a3d45"),
                    font=ctk.CTkFont(size=11, weight="bold" if is_selected or is_today else "normal"),
                    command=lambda d=d_obj: self._choose(d)
                )
                btn.grid(row=r_idx + 1, column=c_idx, padx=2, pady=2)

    def _prev_month(self):
        if self.month == 1:
            self.month = 12
            self.year -= 1
        else:
            self.month -= 1
        self._render_days()

    def _next_month(self):
        if self.month == 12:
            self.month = 1
            self.year += 1
        else:
            self.month += 1
        self._render_days()

    def _choose(self, chosen_date: date):
        self.on_select(chosen_date)
        self.destroy()


class SettingsDialog(ctk.CTkToplevel):
    """Finestra Impostazioni: configurazione credenziali Kimai, file regole e export progetti."""
    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title(f"Impostazioni - ki-talii v{APP_VERSION}")
        self.geometry("640x660")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        ico_file = get_resource_path(os.path.join("assets", "icon.ico"))
        png_file = get_resource_path(os.path.join("assets", "icon.png"))
        try:
            if sys.platform.startswith('win') and os.path.exists(ico_file):
                self.iconbitmap(ico_file)
            elif os.path.exists(png_file):
                img = tk.PhotoImage(file=png_file)
                self.iconphoto(False, img)
        except Exception:
            pass

        self.on_save_callback = on_save_callback
        self.settings = load_settings()

        self._build_ui()

    def _build_ui(self):
        # Titolo
        lbl_title = ctk.CTkLabel(
            self,
            text="⚙️ Impostazioni ki-talii",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        lbl_title.pack(anchor="w", padx=25, pady=(20, 15))

        scroll = ctk.CTkScrollableFrame(self, corner_radius=10)
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        # --- SEZIONE 1: KIMAI ---
        sec_kimai = ctk.CTkFrame(scroll, corner_radius=8)
        sec_kimai.pack(fill="x", padx=5, pady=8)

        ctk.CTkLabel(
            sec_kimai,
            text="CONNESSIONE KIMAI",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray40", "gray60")
        ).pack(anchor="w", padx=15, pady=(12, 6))

        # URL
        ctk.CTkLabel(sec_kimai, text="URL Server Kimai (con /api finale):").pack(anchor="w", padx=15, pady=(4, 0))
        self.entry_kimai_url = ctk.CTkEntry(sec_kimai, placeholder_text="es. https://tt.miodominio.it/api")
        self.entry_kimai_url.insert(0, self.settings.get("kimai_url", ""))
        self.entry_kimai_url.pack(fill="x", padx=15, pady=(2, 8))

        # Username
        ctk.CTkLabel(sec_kimai, text="Nome Utente Kimai:").pack(anchor="w", padx=15, pady=(4, 0))
        self.entry_kimai_user = ctk.CTkEntry(sec_kimai, placeholder_text="es. nome.cognome")
        self.entry_kimai_user.insert(0, self.settings.get("kimai_username", ""))
        self.entry_kimai_user.pack(fill="x", padx=15, pady=(2, 8))

        # API Token
        ctk.CTkLabel(sec_kimai, text="API Token (dal Profilo utente Kimai):").pack(anchor="w", padx=15, pady=(4, 0))
        token_frame = ctk.CTkFrame(sec_kimai, fg_color="transparent")
        token_frame.pack(fill="x", padx=15, pady=(2, 8))

        self.entry_kimai_token = ctk.CTkEntry(token_frame, show="•", placeholder_text="Token API segreto")
        self.entry_kimai_token.insert(0, self.settings.get("kimai_token", ""))
        self.entry_kimai_token.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_show_token = ctk.CTkButton(
            token_frame,
            text="👁️",
            width=36,
            fg_color=("gray80", "gray30"),
            text_color=("black", "white"),
            command=self._toggle_token_visibility
        )
        self.btn_show_token.pack(side="right")

        # Test Connessione
        test_frame = ctk.CTkFrame(sec_kimai, fg_color="transparent")
        test_frame.pack(fill="x", padx=15, pady=(4, 12))

        self.btn_test_kimai = ctk.CTkButton(
            test_frame,
            text="🧪 Verifica Connessione Kimai",
            width=190,
            command=self._test_kimai_connection
        )
        self.btn_test_kimai.pack(side="left")

        self.lbl_kimai_test_res = ctk.CTkLabel(test_frame, text="", font=ctk.CTkFont(size=11, slant="italic"))
        self.lbl_kimai_test_res.pack(side="left", padx=12)

        # --- SEZIONE 2: FILE REGOLE PROGETTI (YAML) ---
        sec_rules = ctk.CTkFrame(scroll, corner_radius=8)
        sec_rules.pack(fill="x", padx=5, pady=8)

        ctk.CTkLabel(
            sec_rules,
            text="REGOLE DI MATCHING (config.yaml)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray40", "gray60")
        ).pack(anchor="w", padx=15, pady=(12, 6))

        ctk.CTkLabel(
            sec_rules,
            text="Seleziona il file YAML dal tuo computer contenente le associazioni:",
            text_color=("gray30", "gray70")
        ).pack(anchor="w", padx=15, pady=(2, 4))

        rules_sel_frame = ctk.CTkFrame(sec_rules, fg_color="transparent")
        rules_sel_frame.pack(fill="x", padx=15, pady=(2, 12))

        self.entry_rules_file = ctk.CTkEntry(rules_sel_frame)
        self.entry_rules_file.insert(0, self.settings.get("rules_file", ""))
        self.entry_rules_file.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse_rules = ctk.CTkButton(
            rules_sel_frame,
            text="📂 Sfoglia...",
            width=90,
            command=self._browse_rules_file
        )
        btn_browse_rules.pack(side="right")

        # --- SEZIONE 3: GENERATORE ELENCO PROGETTI KIMAI ---
        sec_export = ctk.CTkFrame(scroll, corner_radius=8)
        sec_export.pack(fill="x", padx=5, pady=8)

        ctk.CTkLabel(
            sec_export,
            text="GENERATORE DI RIFERIMENTO PROGETTI",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray40", "gray60")
        ).pack(anchor="w", padx=15, pady=(12, 4))

        ctk.CTkLabel(
            sec_export,
            text="Scarica direttamente dal tuo Kimai tutti i clienti, progetti e ID attività,\n"
                 "salvandoli in un file di testo per aiutarti a compilare le regole YAML.",
            text_color=("gray30", "gray70"),
            justify="left"
        ).pack(anchor="w", padx=15, pady=(2, 8))

        btn_export = ctk.CTkButton(
            sec_export,
            text="📄 Genera file elenco progetti Kimai",
            fg_color=("#1f6aa5", "#1f6aa5"),
            height=36,
            command=self._export_kimai_projects
        )
        btn_export.pack(anchor="w", padx=15, pady=(0, 14))

        # --- SEZIONE 4: ACTIVITYWATCHER ---
        sec_aw = ctk.CTkFrame(scroll, corner_radius=8)
        sec_aw.pack(fill="x", padx=5, pady=8)

        ctk.CTkLabel(
            sec_aw,
            text="ACTIVITYWATCHER",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray40", "gray60")
        ).pack(anchor="w", padx=15, pady=(12, 6))

        ctk.CTkLabel(sec_aw, text="URL Server locale ActivityWatcher:").pack(anchor="w", padx=15, pady=(2, 0))
        self.entry_aw_url = ctk.CTkEntry(sec_aw)
        self.entry_aw_url.insert(0, self.settings.get("aw_url", "http://localhost:5600/api/0"))
        self.entry_aw_url.pack(fill="x", padx=15, pady=(2, 12))

        # Bottom buttons
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=25, pady=(5, 20))

        btn_cancel = ctk.CTkButton(
            bottom_frame,
            text="Annulla",
            width=90,
            fg_color=("gray75", "gray30"),
            text_color=("black", "white"),
            command=self.destroy
        )
        btn_cancel.pack(side="left")

        btn_save = ctk.CTkButton(
            bottom_frame,
            text="💾 Salva & Applica",
            width=140,
            fg_color="#107c41",
            hover_color="#0e6b38",
            font=ctk.CTkFont(weight="bold"),
            command=self._save
        )
        btn_save.pack(side="right")

    def _toggle_token_visibility(self):
        if self.entry_kimai_token.cget("show") == "•":
            self.entry_kimai_token.configure(show="")
        else:
            self.entry_kimai_token.configure(show="•")

    def _browse_rules_file(self):
        chosen = filedialog.askopenfilename(
            parent=self,
            title="Seleziona file di configurazione regole",
            filetypes=[("File YAML", "*.yaml *.yml"), ("Tutti i file", "*.*")]
        )
        if chosen:
            self.entry_rules_file.delete(0, "end")
            self.entry_rules_file.insert(0, chosen)

    def _test_kimai_connection(self):
        url = self.entry_kimai_url.get().strip()
        user = self.entry_kimai_user.get().strip()
        token = self.entry_kimai_token.get().strip()

        self.lbl_kimai_test_res.configure(text="Verifica in corso...", text_color="gray60")
        self.btn_test_kimai.configure(state="disabled")

        def test_worker():
            try:
                client = KimaiClient(base_url=url, token=token, username=user)
                v = client.test_connection()
                version = v.get("version", "OK")
                self.after(0, lambda: self.lbl_kimai_test_res.configure(
                    text=f"✓ Connesso (Kimai {version})", text_color="#16a34a"
                ))
            except Exception as e:
                self.after(0, lambda: self.lbl_kimai_test_res.configure(
                    text=f"✗ Errore: {e}", text_color="#dc2626"
                ))
            finally:
                self.after(0, lambda: self.btn_test_kimai.configure(state="normal"))

        threading.Thread(target=test_worker, daemon=True).start()

    def _export_kimai_projects(self):
        url = self.entry_kimai_url.get().strip()
        user = self.entry_kimai_user.get().strip()
        token = self.entry_kimai_token.get().strip()

        save_path = filedialog.asksaveasfilename(
            parent=self,
            title="Salva elenco progetti Kimai",
            defaultextension=".txt",
            initialfile="progetti_kimai.txt",
            filetypes=[("File di testo", "*.txt"), ("Tutti i file", "*.*")]
        )
        if not save_path:
            return

        try:
            total = export_kimai_projects_to_file(url, token, user, save_path)
            messagebox.showinfo(
                "Esportazione riuscita",
                f"✓ File generato con successo!\n\n"
                f"Trovati {total} progetti salvati in:\n{save_path}"
            )
        except Exception as e:
            messagebox.showerror("Errore Esportazione", f"Impossibile esportare i progetti:\n{e}")

    def _save(self):
        new_settings = {
            "kimai_url": self.entry_kimai_url.get().strip(),
            "kimai_username": self.entry_kimai_user.get().strip(),
            "kimai_token": self.entry_kimai_token.get().strip(),
            "rules_file": self.entry_rules_file.get().strip(),
            "aw_url": self.entry_aw_url.get().strip(),
            "theme": self.settings.get("theme", "dark")
        }
        save_settings(new_settings)
        self.on_save_callback(new_settings)
        self.destroy()


class ModernAwToKimaiApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Registrazione ID processo per Windows Taskbar
        if sys.platform.startswith('win'):
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"kitalii.timesheet.sync.{APP_VERSION}")
            except Exception:
                pass

        self.settings = load_settings()
        theme_mode = self.settings.get("theme", "dark")
        ctk.set_appearance_mode(theme_mode)
        ctk.set_default_color_theme("blue")

        self.title(f"ki-talii v{APP_VERSION} ➔ Kimai Sincronizzatore")
        self.geometry("1180x760")
        self.minsize(980, 580)

        # Icona finestra applicazione
        ico_file = get_resource_path(os.path.join("assets", "icon.ico"))
        png_file = get_resource_path(os.path.join("assets", "icon.png"))
        try:
            if sys.platform.startswith('win') and os.path.exists(ico_file):
                self.iconbitmap(ico_file)
            elif os.path.exists(png_file):
                img = tk.PhotoImage(file=png_file)
                self.iconphoto(False, img)
        except Exception as e:
            print(f"[AVVISO] Impossibile impostare icona finestra: {e}")

        # Configurazione unificata
        self.config = load_config()

        # Cache Kimai
        self.kimai_client: Optional[KimaiClient] = None
        self.projects_cache: Dict[int, Dict[str, str]] = {}
        self.activities_cache: Dict[int, str] = {}
        self._init_kimai_client()

        # Stato
        self.current_date = date.today()
        self.matched_blocks: List[TimesheetBlock] = []
        self.unmatched_blocks: List[TimesheetBlock] = []
        self.is_loading = False
        self.msg_queue = queue.Queue()

        self._build_ui()
        self._check_queue()
        self.after(100, self._initial_load)

    def _init_kimai_client(self):
        k_conf = self.config.get("kimai", {})
        if k_conf.get("base_url") and k_conf.get("token"):
            self.kimai_client = KimaiClient(
                base_url=k_conf["base_url"],
                token=k_conf["token"],
                username=k_conf.get("username")
            )

    def _check_queue(self):
        try:
            while not self.msg_queue.empty():
                msg_type, data = self.msg_queue.get_nowait()
                if msg_type == "status":
                    self.lbl_status.configure(text=data)
                elif msg_type == "server_status":
                    self.lbl_server_status.configure(text=data)
                elif msg_type == "aw_offline":
                    self._show_aw_warning_banner(True)
                elif msg_type == "aw_online":
                    self._show_aw_warning_banner(False)
                elif msg_type == "initial_loaded":
                    self.load_day_data()
                elif msg_type == "blocks":
                    matched, unmatched = data
                    self._render_blocks(matched, unmatched)
                elif msg_type == "finish_loading":
                    self._finish_loading()
                elif msg_type == "error":
                    self._show_error(data)
                elif msg_type == "sync_complete":
                    inserted, skipped = data
                    self._on_sync_complete(inserted, skipped)
        except Exception as e:
            print(f"Queue error: {e}")
        finally:
            self.after(50, self._check_queue)

    def _build_ui(self):
        # ---------------------------------------------------------------------
        # BANNER DI AVVISO ACTIVITYWATCHER NON INSTALLATO / OFFLINE
        # ---------------------------------------------------------------------
        self.aw_banner = ctk.CTkFrame(self, fg_color=("#fee2e2", "#450a0a"), height=42, corner_radius=0)

        lbl_aw_warn = ctk.CTkLabel(
            self.aw_banner,
            text="⚠️ ActivityWatcher non è attivo o non è installato sul tuo computer!",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#991b1b", "#fca5a5")
        )
        lbl_aw_warn.pack(side="left", padx=20)

        btn_dl_aw = ctk.CTkButton(
            self.aw_banner,
            text="🌐 Scarica ActivityWatcher",
            height=28,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=open_activitywatcher_download_page
        )
        btn_dl_aw.pack(side="left", padx=10)

        btn_retry_aw = ctk.CTkButton(
            self.aw_banner,
            text="🔄 Riprova",
            height=28,
            width=70,
            fg_color=("gray75", "gray30"),
            text_color=("black", "white"),
            command=self._retry_aw_connection
        )
        btn_retry_aw.pack(side="left", padx=5)

        btn_close_banner = ctk.CTkButton(
            self.aw_banner,
            text="✕",
            width=28,
            height=28,
            fg_color="transparent",
            text_color=("gray30", "gray70"),
            command=lambda: self._show_aw_warning_banner(False)
        )
        btn_close_banner.pack(side="right", padx=15)

        # ---------------------------------------------------------------------
        # 1. TOP HEADER BAR
        # ---------------------------------------------------------------------
        self.header_frame = ctk.CTkFrame(self, corner_radius=0, height=65)
        self.header_frame.pack(fill="x", side="top")

        # Logo brand con icona Trinacria
        self.logo_ctk = None
        png_file = get_resource_path(os.path.join("assets", "icon.png"))
        if os.path.exists(png_file):
            try:
                pil_logo = Image.open(png_file)
                self.logo_ctk = ctk.CTkImage(light_image=pil_logo, dark_image=pil_logo, size=(28, 28))
            except Exception as e:
                print(f"[AVVISO] Impossibile caricare logo header: {e}")

        lbl_brand = ctk.CTkLabel(
            self.header_frame,
            text="  ki-talii" if self.logo_ctk else "⚡ ki-talii",
            image=self.logo_ctk,
            compound="left",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        lbl_brand.pack(side="left", padx=(15, 20))

        # Navigazione Data
        btn_prev = ctk.CTkButton(
            self.header_frame,
            text="◀ Ieri",
            width=65,
            height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray10", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_prev_day
        )
        btn_prev.pack(side="left", padx=2)

        self.var_date = tk.StringVar(value=self.current_date.strftime("%Y-%m-%d"))
        self.entry_date = ctk.CTkEntry(
            self.header_frame,
            textvariable=self.var_date,
            width=115,
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            justify="center"
        )
        self.entry_date.pack(side="left", padx=4)
        self.entry_date.bind("<Return>", lambda e: self._on_date_entered())

        btn_next = ctk.CTkButton(
            self.header_frame,
            text="Domani ▶",
            width=75,
            height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray10", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._on_next_day
        )
        btn_next.pack(side="left", padx=2)

        btn_cal = ctk.CTkButton(
            self.header_frame,
            text="📅",
            width=36,
            height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray10", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._open_calendar
        )
        btn_cal.pack(side="left", padx=2)

        btn_today = ctk.CTkButton(
            self.header_frame,
            text="Oggi",
            width=55,
            height=32,
            command=self._on_today
        )
        btn_today.pack(side="left", padx=(4, 12))

        self.btn_refresh = ctk.CTkButton(
            self.header_frame,
            text="🔄 Ricarica",
            width=85,
            height=32,
            fg_color=("#1f6aa5", "#1f6aa5"),
            command=self.load_day_data
        )
        self.btn_refresh.pack(side="left", padx=2)

        # Pulsante Impostazioni
        self.btn_settings = ctk.CTkButton(
            self.header_frame,
            text="⚙️ Impostazioni",
            width=120,
            height=32,
            fg_color=("gray85", "gray25"),
            text_color=("gray10", "gray90"),
            hover_color=("gray75", "gray35"),
            command=self._open_settings
        )
        self.btn_settings.pack(side="left", padx=10)

        # Selettore Dark / Light Mode (A destra)
        self.theme_switch = ctk.CTkSegmentedButton(
            self.header_frame,
            values=["🌙 Dark", "☀️ Light"],
            width=135,
            height=32,
            command=self._on_theme_change
        )
        current_theme_label = "🌙 Dark" if self.settings.get("theme") == "dark" else "☀️ Light"
        self.theme_switch.set(current_theme_label)
        self.theme_switch.pack(side="right", padx=(10, 20))

        # Status badge connessione
        self.lbl_server_status = ctk.CTkLabel(
            self.header_frame,
            text="Verifica stato...",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color=("gray50", "gray60")
        )
        self.lbl_server_status.pack(side="right", padx=10)

        # ---------------------------------------------------------------------
        # 2. METRICS / STATS CARDS
        # ---------------------------------------------------------------------
        stats_frame = ctk.CTkFrame(self, fg_color="transparent")
        stats_frame.pack(fill="x", padx=20, pady=(12, 8))

        self.card_kimai = ctk.CTkFrame(stats_frame, corner_radius=10, height=70)
        self.card_kimai.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(self.card_kimai, text="TEMPO DA INVIARE", font=ctk.CTkFont(size=10, weight="bold"), text_color=("gray40", "gray60")).pack(anchor="w", padx=15, pady=(8, 0))
        self.lbl_kimai_time = ctk.CTkLabel(self.card_kimai, text="0h 00m", font=ctk.CTkFont(size=22, weight="bold"), text_color=("#2ecc71", "#2ecc71"))
        self.lbl_kimai_time.pack(anchor="w", padx=15, pady=(0, 8))

        self.card_blocks = ctk.CTkFrame(stats_frame, corner_radius=10, height=70)
        self.card_blocks.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ctk.CTkLabel(self.card_blocks, text="BLOCCHI CONSOLIDATI", font=ctk.CTkFont(size=10, weight="bold"), text_color=("gray40", "gray60")).pack(anchor="w", padx=15, pady=(8, 0))
        self.lbl_blocks_count = ctk.CTkLabel(self.card_blocks, text="0 intervalli", font=ctk.CTkFont(size=22, weight="bold"), text_color=("#3498db", "#3498db"))
        self.lbl_blocks_count.pack(anchor="w", padx=15, pady=(0, 8))

        self.card_unmatched = ctk.CTkFrame(stats_frame, corner_radius=10, height=70)
        self.card_unmatched.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(self.card_unmatched, text="NON RICONOSCIUTO", font=ctk.CTkFont(size=10, weight="bold"), text_color=("gray40", "gray60")).pack(anchor="w", padx=15, pady=(8, 0))
        self.lbl_unmatched_time = ctk.CTkLabel(self.card_unmatched, text="0m", font=ctk.CTkFont(size=22, weight="bold"), text_color=("#e67e22", "#e67e22"))
        self.lbl_unmatched_time.pack(anchor="w", padx=15, pady=(0, 8))

        # ---------------------------------------------------------------------
        # 3. TABVIEW PRINCIPALE
        # ---------------------------------------------------------------------
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(4, 10))

        self.tab_kimai = self.tabview.add(" 🕒 Intervalli pronti per Kimai ")
        self.tab_unmatched = self.tabview.add(" ❓ Attività non riconosciute ")

        self._build_matched_tab()
        self._build_unmatched_tab()

        # ---------------------------------------------------------------------
        # 4. BOTTOM BAR
        # ---------------------------------------------------------------------
        bottom_frame = ctk.CTkFrame(self, corner_radius=0, height=65)
        bottom_frame.pack(fill="x", side="bottom")

        self.lbl_status = ctk.CTkLabel(
            bottom_frame,
            text="Pronto.",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray70")
        )
        self.lbl_status.pack(side="left", padx=(25, 10))

        lbl_version_badge = ctk.CTkLabel(
            bottom_frame,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("gray50", "gray50")
        )
        lbl_version_badge.pack(side="left", padx=5)

        self.btn_send_kimai = ctk.CTkButton(
            bottom_frame,
            text="🚀 Manda a Kimai",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#107c41",
            hover_color="#0e6b38",
            height=42,
            corner_radius=8,
            command=self._confirm_and_send
        )
        self.btn_send_kimai.pack(side="right", padx=25, pady=12)

    def _show_aw_warning_banner(self, show: bool):
        if show:
            self.aw_banner.pack(fill="x", side="top", before=self.header_frame)
        else:
            self.aw_banner.pack_forget()

    def _build_matched_tab(self):
        hdr = ctk.CTkFrame(self.tab_kimai, height=30, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(2, 6))

        ctk.CTkLabel(hdr, text="ORARIO", width=125, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="DURATA", width=85, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="CLIENTE", width=170, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="PROGETTO", width=220, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="ATTIVITÀ", width=110, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="FINESTRE CAMPIONATE", anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left", fill="x", expand=True)

        self.scroll_matched = ctk.CTkScrollableFrame(self.tab_kimai, corner_radius=8)
        self.scroll_matched.pack(fill="both", expand=True, padx=5, pady=(0, 5))

    def _build_unmatched_tab(self):
        hdr = ctk.CTkFrame(self.tab_unmatched, height=30, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(2, 6))

        ctk.CTkLabel(hdr, text="ORARIO", width=125, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="DURATA", width=85, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="APPLICAZIONI", width=230, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left")
        ctk.CTkLabel(hdr, text="TITOLI FINESTRE", anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=("gray40", "gray60")).pack(side="left", fill="x", expand=True)

        self.scroll_unmatched = ctk.CTkScrollableFrame(self.tab_unmatched, corner_radius=8)
        self.scroll_unmatched.pack(fill="both", expand=True, padx=5, pady=(0, 5))

    def _open_settings(self):
        SettingsDialog(self, self._on_settings_saved)

    def _on_settings_saved(self, new_settings: Dict[str, Any]):
        self.settings = new_settings
        self.config = load_config()
        self._init_kimai_client()
        self.load_day_data()

    def _on_theme_change(self, mode: str):
        theme = "dark" if "Dark" in mode else "light"
        ctk.set_appearance_mode(theme)
        self.settings["theme"] = theme
        save_settings(self.settings)

    def _retry_aw_connection(self):
        aw_online = check_activitywatcher_online(self.settings.get("aw_url", "http://localhost:5600/api/0"))
        if aw_online:
            self._show_aw_warning_banner(False)
            self._set_status("ActivityWatcher connesso!")
            self.load_day_data()
        else:
            messagebox.showwarning(
                "Ancora Non Raggiungibile",
                "ActivityWatcher continua a non rispondere su localhost:5600.\n"
                "Assicurati che sia avviato in background o scaricalo dal sito ufficiale."
            )

    def _initial_load(self):
        def worker():
            self._set_status("Inizializzazione Kimai e ActivityWatcher...")
            kimai_ok = False
            aw_ok = False

            # Test Kimai
            if self.kimai_client:
                try:
                    self.kimai_client.test_connection()
                    customers = self.kimai_client.get_customers()
                    projects = self.kimai_client.get_projects()
                    activities = self.kimai_client.get_activities()

                    self.projects_cache = {
                        p["id"]: {
                            "name": p["name"],
                            "customer": customers.get(p.get("customer"), "")
                        } for p in projects
                    }
                    self.activities_cache = {a["id"]: a["name"] for a in activities}
                    kimai_ok = True
                except Exception as e:
                    print(f"Kimai error: {e}")

            # Test AW
            aw_url = self.settings.get("aw_url", "http://localhost:5600/api/0")
            aw_ok = check_activitywatcher_online(aw_url)

            if not aw_ok:
                self.msg_queue.put(("aw_offline", None))
            else:
                self.msg_queue.put(("aw_online", None))

            status_str = f"Kimai: {'✓ Online' if kimai_ok else '✗ Offline'}  |  AW: {'✓ Online' if aw_ok else '✗ Non attivo'}"
            self.msg_queue.put(("server_status", status_str))
            self.msg_queue.put(("initial_loaded", None))

        threading.Thread(target=worker, daemon=True).start()

    def _on_prev_day(self):
        self.current_date -= timedelta(days=1)
        self.var_date.set(self.current_date.strftime("%Y-%m-%d"))
        self.load_day_data()

    def _on_next_day(self):
        self.current_date += timedelta(days=1)
        self.var_date.set(self.current_date.strftime("%Y-%m-%d"))
        self.load_day_data()

    def _on_today(self):
        self.current_date = date.today()
        self.var_date.set(self.current_date.strftime("%Y-%m-%d"))
        self.load_day_data()

    def _on_date_entered(self):
        text = self.var_date.get().strip()
        try:
            self.current_date = datetime.strptime(text, "%Y-%m-%d").date()
            self.load_day_data()
        except ValueError:
            messagebox.showerror("Errore Data", "Usa il formato YYYY-MM-DD (es. 2026-11-04).")

    def _open_calendar(self):
        ModernCalendarDialog(self, self.current_date, self._on_date_from_calendar)

    def _on_date_from_calendar(self, d: date):
        self.current_date = d
        self.var_date.set(self.current_date.strftime("%Y-%m-%d"))
        self.load_day_data()

    def _set_status(self, msg: str):
        self.msg_queue.put(("status", msg))

    def load_day_data(self):
        if self.is_loading:
            return

        self.is_loading = True
        self.btn_refresh.configure(state="disabled")
        self.btn_send_kimai.configure(state="disabled")
        self._set_status(f"Estrazione attività per {self.current_date.strftime('%d/%m/%Y')}...")

        target = self.current_date

        def worker():
            try:
                aw_url = self.settings.get("aw_url", "http://localhost:5600/api/0")
                aw = ActivityWatcherClient(aw_url)

                start_dt = datetime.combine(target, time.min).astimezone()
                end_dt = datetime.combine(target, time.max).astimezone()

                raw_events = aw.query_active_window_events(start_dt, end_dt)

                classifier = EventClassifier(self.config)
                classified_events: List[ClassifiedEvent] = []

                for ev in raw_events:
                    ts = datetime.fromisoformat(ev["timestamp"]).astimezone()
                    dur = float(ev.get("duration", 0.0))
                    data = ev.get("data", {})
                    classified = classifier.classify(data.get("app", ""), data.get("title", ""), ts, dur)
                    classified_events.append(classified)

                merger = IntervalMerger(self.config)
                blocks = merger.merge_events(classified_events)

                matched = [b for b in blocks if not b.is_unmatched]
                unmatched = [b for b in blocks if b.is_unmatched]

                self.msg_queue.put(("blocks", (matched, unmatched)))
            except Exception as e:
                self.msg_queue.put(("error", f"Errore estrazione:\n{e}"))
            finally:
                self.msg_queue.put(("finish_loading", None))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_loading(self):
        self.is_loading = False
        self.btn_refresh.configure(state="normal")
        self.btn_send_kimai.configure(state="normal")

    def _show_error(self, err_msg: str):
        self._set_status(f"Errore: {err_msg}")
        messagebox.showerror("Errore", err_msg)

    def _render_blocks(self, matched: List[TimesheetBlock], unmatched: List[TimesheetBlock]):
        self.matched_blocks = matched
        self.unmatched_blocks = unmatched

        for w in self.scroll_matched.winfo_children():
            w.destroy()
        for w in self.scroll_unmatched.winfo_children():
            w.destroy()

        total_kimai_secs = 0.0
        total_unmatched_secs = 0.0

        if not matched:
            no_data = ctk.CTkLabel(
                self.scroll_matched,
                text="Nessun intervallo registrato per questa data.",
                font=ctk.CTkFont(size=13, slant="italic"),
                text_color=("gray50", "gray60")
            )
            no_data.pack(pady=40)
        else:
            for b in matched:
                total_kimai_secs += b.active_duration
                proj_info = self.projects_cache.get(b.project_id, {})
                proj_name = proj_info.get("name") or b.rule_name
                cust_name = proj_info.get("customer", "-")
                act_name = self.activities_cache.get(b.activity_id, f"Attività #{b.activity_id}")

                time_span = f"{b.start.strftime('%H:%M')} - {b.end.strftime('%H:%M')}"
                dur_str = format_duration(b.active_duration)
                details = " | ".join(b.sample_titles[:3]) if b.sample_titles else ", ".join(list(b.apps)[:2])

                row = ctk.CTkFrame(self.scroll_matched, corner_radius=8, fg_color=("gray92", "#23272d"), height=46)
                row.pack(fill="x", pady=3, padx=2)

                time_badge = ctk.CTkLabel(
                    row,
                    text=time_span,
                    width=115,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    fg_color=("#dbeafe", "#1e3a8a"),
                    text_color=("#1e40af", "#93c5fd"),
                    corner_radius=6
                )
                time_badge.pack(side="left", padx=(8, 10), pady=6)

                dur_lbl = ctk.CTkLabel(
                    row,
                    text=dur_str,
                    width=75,
                    anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=("#16a34a", "#4ade80")
                )
                dur_lbl.pack(side="left", padx=(0, 10))

                cust_lbl = ctk.CTkLabel(
                    row,
                    text=cust_name,
                    width=160,
                    anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold")
                )
                cust_lbl.pack(side="left", padx=(0, 10))

                proj_lbl = ctk.CTkLabel(
                    row,
                    text=proj_name,
                    width=210,
                    anchor="w",
                    font=ctk.CTkFont(size=12)
                )
                proj_lbl.pack(side="left", padx=(0, 10))

                act_lbl = ctk.CTkLabel(
                    row,
                    text=act_name,
                    width=100,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    fg_color=("gray82", "#323842"),
                    text_color=("gray20", "gray85"),
                    corner_radius=6
                )
                act_lbl.pack(side="left", padx=(0, 12), pady=6)

                det_lbl = ctk.CTkLabel(
                    row,
                    text=details,
                    anchor="w",
                    font=ctk.CTkFont(size=11),
                    text_color=("gray40", "gray55")
                )
                det_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))

        if not unmatched:
            no_unmatched = ctk.CTkLabel(
                self.scroll_unmatched,
                text="Tutte le attività di questa data sono state riconosciute!",
                font=ctk.CTkFont(size=13, slant="italic"),
                text_color=("#16a34a", "#4ade80")
            )
            no_unmatched.pack(pady=40)
        else:
            for b in unmatched:
                total_unmatched_secs += b.active_duration
                time_span = f"{b.start.strftime('%H:%M')} - {b.end.strftime('%H:%M')}"
                dur_str = format_duration(b.active_duration)
                apps_str = ", ".join(list(b.apps)[:3])
                titles_str = " | ".join(b.sample_titles[:3])

                row = ctk.CTkFrame(self.scroll_unmatched, corner_radius=8, fg_color=("gray92", "#23272d"), height=46)
                row.pack(fill="x", pady=3, padx=2)

                time_badge = ctk.CTkLabel(
                    row,
                    text=time_span,
                    width=115,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    fg_color=("gray80", "#3a3f4a"),
                    corner_radius=6
                )
                time_badge.pack(side="left", padx=(8, 10), pady=6)

                dur_lbl = ctk.CTkLabel(
                    row,
                    text=dur_str,
                    width=75,
                    anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=("#ea580c", "#fb923c")
                )
                dur_lbl.pack(side="left", padx=(0, 10))

                apps_lbl = ctk.CTkLabel(
                    row,
                    text=apps_str,
                    width=220,
                    anchor="w",
                    font=ctk.CTkFont(size=12, weight="bold")
                )
                apps_lbl.pack(side="left", padx=(0, 10))

                det_lbl = ctk.CTkLabel(
                    row,
                    text=titles_str,
                    anchor="w",
                    font=ctk.CTkFont(size=11),
                    text_color=("gray40", "gray55")
                )
                det_lbl.pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.lbl_kimai_time.configure(text=format_duration(total_kimai_secs))
        self.lbl_blocks_count.configure(text=f"{len(matched)} blocchi")
        self.lbl_unmatched_time.configure(text=format_duration(total_unmatched_secs))
        self._set_status(f"Dati aggiornati al {self.current_date.strftime('%d/%m/%Y')}. {len(matched)} blocchi pronti per l'invio.")

    def _confirm_and_send(self):
        if not self.matched_blocks:
            messagebox.showinfo("Nessun dato", "Non ci sono intervalli da inviare per questa data.")
            return

        if not self.kimai_client:
            messagebox.showerror("Errore Kimai", "Configurazione Kimai non valida. Verifica in Impostazioni.")
            return

        total_secs = sum(b.active_duration for b in self.matched_blocks)
        dur_text = format_duration(total_secs)
        date_str = self.current_date.strftime("%d/%m/%Y")

        confirm = messagebox.askyesno(
            "Conferma invio a Kimai",
            f"Vuoi inviare {len(self.matched_blocks)} blocchi di lavoro a Kimai?\n\n"
            f"📅 Data: {date_str}\n"
            f"⏱️ Tempo totale: {dur_text}\n\n"
            f"I record già presenti con lo stesso orario non verranno duplicati.",
            icon="question"
        )
        if not confirm:
            return

        self.btn_send_kimai.configure(state="disabled")
        self._set_status("Invio dei timesheet a Kimai in corso...")

        def sync_worker():
            try:
                start_dt = datetime.combine(self.current_date, time.min)
                end_dt = datetime.combine(self.current_date, time.max)
                existing = self.kimai_client.get_timesheets(start_dt, end_dt)
                tag = self.config.get("settings", {}).get("tag", "ki-talii")

                inserted = 0
                skipped = 0

                for b in self.matched_blocks:
                    is_dup = False
                    for ex in existing:
                        ex_begin = datetime.fromisoformat(ex["begin"]).astimezone()
                        if ex.get("project") == b.project_id:
                            if abs((ex_begin - b.start).total_seconds()) < 120:
                                is_dup = True
                                break

                    if is_dup:
                        skipped += 1
                        continue

                    desc = ""
                    if b.sample_titles:
                        desc = "Finestre: " + "; ".join(b.sample_titles[:3])

                    self.kimai_client.create_timesheet(
                        begin=b.start,
                        end=b.end,
                        project_id=b.project_id,
                        activity_id=b.activity_id,
                        description=desc,
                        tags=tag
                    )
                    inserted += 1

                self.msg_queue.put(("sync_complete", (inserted, skipped)))
            except Exception as e:
                self.msg_queue.put(("error", f"Errore durante l'invio a Kimai:\n{e}"))
            finally:
                self.msg_queue.put(("finish_loading", None))

        threading.Thread(target=sync_worker, daemon=True).start()

    def _on_sync_complete(self, inserted: int, skipped: int):
        self._set_status(f"Completato: {inserted} inseriti, {skipped} già presenti.")
        messagebox.showinfo(
            "Sincronizzazione completata",
            f"✓ Operazione conclusa con successo!\n\n"
            f"• Inseriti su Kimai: {inserted}\n"
            f"• Già presenti (ignorati): {skipped}"
        )


def main():
    app = ModernAwToKimaiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
