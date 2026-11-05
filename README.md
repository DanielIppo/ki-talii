# ki-talii

Sincronizzazione automatica tra **ActivityWatcher** e **Kimai** preservando gli **intervalli orari reali**.

---

## ✨ Nuove Funzionalità (Branch `executable`)

### 1. ⚙️ Pannello Impostazioni Integrato
Non serve più modificare file `.env` a mano se usi l'app installata! Cliccando su **`⚙️ Impostazioni`** nell'header:
* **Credenziali Kimai:** Configura URL del server, Nome Utente e API Token con test di connessione in tempo reale.
* **Caricamento Regole da PC:** Puoi scegliere con un selettore file (`📂 Sfoglia...`) qualsiasi file `config.yaml` presente sul tuo computer.
* **📄 Generatore Elenco Progetti Kimai:** Un pulsante dedicato che interroga le API del tuo Kimai e salva sul tuo computer un file `.txt` pulito con tutti i clienti, progetti e ID attività, pronto da copiare/incollare nelle tue regole.

### 2. 🔍 Controllo all'Avvio di ActivityWatcher
All'avvio, l'applicazione verifica se ActivityWatcher è attivo:
* Se è spento o non installato, mostra un banner chiaro in alto con il pulsante **`🌐 Scarica ActivityWatcher`** che rimanda alla pagina ufficiale di download.

---

## 📦 Creazione Eseguibili & Installer

### 🪟 Windows (.exe / Installer)
1. **Compilazione rapida eseguibile:**
   Esegui lo script:
   ```cmd
   packaging\windows\build_windows.bat
   ```
   Troverai l'applicazione standalone in `dist\ki-talii\ki-talii.exe`.
2. **Creazione Installer Wizard:**
   Apri il file `packaging\windows\installer.iss` con [Inno Setup](https://jrsoftware.org/isinfo.php) e clicca *Compile*. Genererà `ki-talii-setup-x64.exe` con icona sul desktop e disinstallatore.

### 🐧 Linux (.deb per Ubuntu, Debian, Mint, Pop!_OS)
Esegui sul tuo sistema Linux:
```bash
chmod +x packaging/linux/build_deb.sh
./packaging/linux/build_deb.sh
```
Verrà generato il pacchetto `ki-talii_1.1_amd64.deb` installabile con:
```bash
sudo dpkg -i ki-talii_1.1_amd64.deb
```

### 🚀 Compilazione Automatica su GitHub Actions
È stato configurato il workflow [`.github/workflows/build_releases.yml`](.github/workflows/build_releases.yml):
Ad ogni `git push` sul branch `executable`, GitHub avvia in automatico una macchina Windows e una macchina Ubuntu, compilando sia il file **`.zip` per Windows** sia il pacchetto **`.deb` per Linux**, pronti per il download nella sezione Actions / Release!

---

## 💻 Avvio in modalità sviluppo
```bash
python gui.py
```
oppure:
```bash
python sync.py --sync
```

---

## 🎯 Guida: Come configurare e ottimizzare `config.yaml`

Il file `config.yaml` (o qualsiasi file `.yaml` tu scelga dal pannello **`⚙️ Impostazioni`** dell'applicazione) definisce il modo in cui **ki-talii** traduce le finestre e i processi registrati da ActivityWatcher in **Clienti, Progetti e Attività** su Kimai.

Grazie all'algoritmo di consolidamento (supporto a record paralleli, assorbimento micro-pause, protezione anti-blip ed eredità automatica del contesto di sviluppo), con poche regole scritte bene otterrai un resoconto giornaliero perfetto.

---

### 1. 📋 Procurarsi gli ID di Kimai in 1 secondo
Prima di scrivere le regole a mano:
1. Apri **ki-talii** e clicca su **`⚙️ Impostazioni`** in alto a destra.
2. Assicurati che l'URL Kimai, l'utente e il token API siano configurati (usa il pulsante *Test Connessione*).
3. Clicca su **`📄 Esporta Elenco Progetti Kimai`**.
4. Verrà salvato sul tuo computer un file `.txt` ordinato con tutti i tuoi clienti, i relativi **ID Progetto** e gli **ID Attività** (es. *18 = Sviluppo, 19 = Assistenza, 4 = Call/Meeting*).

---

### 2. 🪜 Regola d'oro: Ordine delle regole (Dal più specifico al più generico)
Le regole vengono lette **dall'alto verso il basso** (*first-match wins*): la prima regola che fa scattare un pattern assegna il progetto.  
Organizza sempre il tuo file seguendo questo ordine logico:

1. **📞 Meeting e Call (Priorità massima):** Regole per riunioni (Google Meet, Teams, Zoom) con ID attività dedicato alle Call. Se messe in cima, catturano la riunione anche se hai sotto un editor aperto.
2. **🎫 Ticket o Assistenza Specifica:** URL di ticket, Jira, GitLab issues o portali clienti.
3. **💻 Repository e Cartelle di Sviluppo:** Nomi delle cartelle aperte negli IDE (Visual Studio Code, Visual Studio, PhpStorm, ecc.).
4. **🌐 Ambienti di sviluppo e domini web:** Schede del browser con domini locali o di staging (es. `localhost:3000`, `staging.miocliente.it`).

---

### 3. 🧠 Smart Context: Non serve mappare i tool neutri!
ki-talii include un sistema intelligente di **Dominant Context Inheritance** per i software neutri usati dagli sviluppatori:
* **Database & Query:** `DBeaver`, `Lens`, `pgAdmin`, `MySQL Workbench`, fogli di calcolo `Excel`/`Calc`.
* **API & Container:** `Postman`, `Insomnia`, `Docker Desktop`, finestre browser con `Swagger UI`, `Keycloak` o `DevTools`.

> [!TIP]
> **Non serve creare regole per DBeaver, Postman o Swagger!**  
> Se stai programmando sul "Progetto A" in VS Code e apri DBeaver per fare una query, ki-talii rileva il tool neutro e gli assegna in automatico il progetto dominante dell'ultimo quarto d'ora.

---

### 4. 📝 Esempio di `config.yaml` ottimizzato

```yaml
kimai:
  base_url: "${KIMAI_BASE_URL}"
  token: "${KIMAI_TOKEN}"
  username: "${KIMAI_USERNAME}"

activitywatcher:
  base_url: "${ACTIVITYWATCHER_BASE_URL}"

settings:
  # ID Attività predefinita se una regola non la specifica
  default_activity_id: 18

  # Tolleranza micro-pausa (secondi) prima di considerare chiusa una sessione (5 minuti)
  max_gap_seconds: 300

  # Pausa massima tra blocchi dello stesso progetto per unirli in una sola sessione (20 minuti)
  max_merge_gap_seconds: 1200

  # Tempo minimo di lavoro attivo affinché un blocco venga sincronizzato (2 minuti)
  min_duration_seconds: 120

  # Tag predefinito assegnato su Kimai
  tag: "ki-talii"

# Applicazioni personali o di sistema da ignorare completamente
ignored_apps:
  - "whatsapp.exe"
  - "whatsapp.root.exe"
  - "telegram.exe"
  - "discord.exe"
  - "spotify.exe"
  - "lockapp.exe"
  - "shellexperiencehost.exe"
  - "applicationframehost.exe"
  - "taskmgr.exe"
  - "snippingtool.exe"

# Titoli di finestre da ignorare (Regex case-insensitive)
ignored_patterns:
  - "^(Nuova scheda|New Tab) - (Google Chrome|Brave|Microsoft​ Edge)$"
  - "Task Switching"
  - "Blocco note"
  - "Calcolatrice"

# Regole di classificazione (Lette dall'alto verso il basso)
rules:
  # ============================================================================
  # 1. CALL E RIUNIONI (Attività Call)
  # ============================================================================
  - name: "Cliente A - Call"
    project_id: 10
    activity_id: 4               # ID Attività 'Call'
    patterns:
      - "(?i)Meet - STANDUP-CLIENTEA"
      - "(?i)Call Cliente A"

  # ============================================================================
  # 2. ASSISTENZA / TICKET (Attività Assistenza)
  # ============================================================================
  - name: "Cliente B - Assistenza e Supporto"
    project_id: 20
    activity_id: 19              # ID Attività 'Assistenza'
    patterns:
      - "(?i)portale-ticket-clienteb"
      - "(?i)clienteb-cargo"

  # ============================================================================
  # 3. SVILUPPO (Attività Sviluppo)
  # ============================================================================
  - name: "Cliente A - Gestionale Cloud"
    project_id: 10
    activity_id: 18              # ID Attività 'Sviluppo'
    patterns:
      # Titolo della cartella di progetto in VS Code / Visual Studio
      - "(?i)gestionale-cloud-app"
      # Titoli delle pagine web dell'app o ambiente locale
      - "(?i)localhost:3000"
      - "(?i)Gestionale Cloud - Brave"

  - name: "Cliente C - API Microservizi"
    project_id: 30
    activity_id: 18
    patterns:
      - "(?i)clientec-api"
      - "(?i)clientec-worker"
```

---

### 5. 💡 Consigli Pratici per Regole Impeccabili

* **Usa sempre `(?i)` nei pattern:** Significa *case-insensitive* e fa sì che `(?i)officina` riconosca sia `officina`, sia `Officina`, sia `OFFICINA`.
* **Sfrutta la cartella dell'editor:** In Visual Studio Code o negli editor moderni, il titolo della finestra include sempre il nome della cartella del progetto (es. `mio-progetto - Visual Studio Code`). Usare `(?i)mio-progetto` è il modo più rapido ed efficace per coprire tutto lo sviluppo.
* **Guarda le "Attività non riconosciute":** Se a fine giornata vedi del tempo non riconosciuto nella schermata di ki-talii, guarda i titoli di esempio mostrati in tabella: ti basterà prendere una parola chiave univoca e aggiungerla alla regola corrispondente.
* **Filtro opzionale per applicazione (`apps`):** Se desideri che una regola sia valida solo per un determinato programma, puoi aggiungere il campo opzionale `apps`:
  ```yaml
  - name: "Cliente A - Grafica e Mockup"
    project_id: 10
    activity_id: 18
    apps:
      - "figma.exe"
    patterns:
      - "(?i)Cliente A"
  ```

