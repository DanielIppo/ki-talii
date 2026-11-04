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
Verrà generato il pacchetto `ki-talii_1.0.0_amd64.deb` installabile con:
```bash
sudo dpkg -i ki-talii_1.0.0_amd64.deb
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
