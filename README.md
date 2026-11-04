# ki-talii

Sincronizzazione intelligente tra **ActivityWatcher** e **Kimai** preservando gli **intervalli orari reali**.

---

## 🖥️ Interfaccia Grafica

Puoi avviare l'interfaccia grafica in due modi:
1. Facendo doppio clic su [**`avvia_interfaccia.bat`**](file:///C:/progetti/personali/ki-talii/avvia_interfaccia.bat)
2. Oppure da terminale:
   ```bash
   python gui.py
   # oppure
   python sync.py --gui
   ```

### Funzionalità dell'Interfaccia:
* **Tema Dark / Light:** Switch rapido in alto a destra per alternare tra Dark Mode e Light Mode.
* **Metriche immediate:** Ore Kimai calcolate, numero di blocchi consolidati e tempo non riconosciuto.
* **Selezione Data:** Di default oggi, con navigazione rapida `◀ Ieri`, `Domani ▶`, `Oggi` e `📅 Calendario`.
* **Tabella Intervalli Kimai:** Mostra ogni sessione con:
  * Orario di **Inizio** e **Fine** (es. `15:43 - 17:32`).
  * **Durata** netta lavorata.
  * Nome del **Cliente** e del **Progetto** Kimai.
  * Nome dell'**Attività** (es. *Sviluppo*, *Assistenza*, *Sistemistica*).
  * Anteprima delle finestre rilevate.
* **Scheda "Attività non riconosciute":** Permette di vedere se ci sono ore lavorate su progetti non ancora associati a una regola.
* **Tasto "🚀 Manda a Kimai":** Chiede conferma con il riassunto delle ore e invia automaticamente i record alle API di Kimai, escludendo duplicati già presenti.

---

## ⚡ Uso da Riga di Comando (CLI)

Se preferisci usare il terminale:

### 1. Anteprima dei tempi (senza inviare nulla)
```bash
python sync.py
```

### 2. Sincronizzazione con invio a Kimai
```bash
python sync.py --sync
```
Oppure fai doppio clic su `fine_giornata.bat`.

### 3. Vedere tutti i Clienti, Progetti e Attività con i loro ID
```bash
python sync.py --list-kimai
```

### 4. Consultare i titoli grezzi catturati da ActivityWatcher
```bash
python sync.py --raw
```

---

## ⚙️ Regole di Matching (`config.yaml`)

Tutte le regole si trovano nel file [**`config.yaml`**](file:///C:/progetti/personali/ki-talii/config.yaml). Contiene già tutti i 38 progetti del tuo Kimai associati alle rispettive parole chiave e regex.
