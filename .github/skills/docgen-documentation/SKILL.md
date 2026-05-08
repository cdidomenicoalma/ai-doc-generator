---
name: docgen-documentation
description: Genera documentazione tecnica e funzionale usando DocGen con installazione e aggiornamento automatico da GitHub Release
---

# DocGen Documentation Skill

## Obiettivo
Eseguire DocGen automaticamente:
- installazione se non presente
- aggiornamento se versione obsoleta
- generazione documentazione

## Parametri
- Repository release DocGen: `cdidomenicoalma/ai-doc-generator`
- Latest release API: `https://api.github.com/repos/cdidomenicoalma/ai-doc-generator/releases/latest`
- Asset atteso: `docgen_<version>.zip`
- Cartella root dentro lo zip: `ai-doc-generator`
- Python preferito: `python3`
- Fallback Python: `python`
- Cleanup default: `true`
- Render default: `false`

---

## Step 1 — Verifica ambiente Python

1. Prova a usare `python3`.
2. Se `python3` non è disponibile, usa `python`.
3. Usa SEMPRE lo stesso interprete Python per tutte le operazioni successive.

---

## Step 2 — Verifica installazione locale di DocGen

Verifica se `docgen` è installato e leggine la versione:

```bash
python3 -c "import docgen; print(docgen.__version__)"
```

Fallback:

```bash
python -c "import docgen; print(docgen.__version__)"
```

Se il comando fallisce, considera `docgen` non installato.

IMPORTANTE:
- se stai lavorando dentro il repository sorgente di DocGen, il package locale potrebbe falsare il controllo;
- in caso di dubbio, considera la versione locale non affidabile e procedi con aggiornamento/installazione dalla release.

---

## Step 3 — Recupera la latest release da GitHub

Interroga:

`https://api.github.com/repos/cdidomenicoalma/ai-doc-generator/releases/latest`

Dalla risposta recupera:
- `tag_name` → versione release, ad esempio `v1.0.1`
- l'asset ZIP corretto, ad esempio `docgen_1.0.1.zip`
- `browser_download_url` dell'asset ZIP

La versione remota si ottiene rimuovendo il prefisso `v` da `tag_name`.

Esempio atteso di download:
`https://github.com/cdidomenicoalma/ai-doc-generator/releases/download/v1.0.1/docgen_1.0.1.zip`

---

## Step 4 — Confronto versioni

Regole:
- se `docgen` non è installato → installa latest release
- se la versione locale è diversa da quella remota → aggiorna
- se la versione locale coincide con quella remota → continua senza reinstallare

---

## Step 5 — Installazione / aggiornamento da release ZIP

### 5.1 Scarica lo ZIP della release

Su PowerShell puoi usare:

```powershell
Invoke-WebRequest -Uri "<DOWNLOAD_URL>" -OutFile "docgen.zip"
```

In alternativa:

```bash
curl -L -o docgen.zip <DOWNLOAD_URL>
```

### 5.2 Estrai lo ZIP

Su PowerShell:

```powershell
Expand-Archive docgen.zip -DestinationPath docgen_tmp -Force
```

In alternativa:

```bash
unzip docgen.zip -d docgen_tmp
```

### 5.3 Installa / aggiorna

Installa dalla cartella estratta `ai-doc-generator`:

```bash
python3 -m pip install --upgrade ./docgen_tmp/ai-doc-generator
```

Fallback:

```bash
python -m pip install --upgrade ./docgen_tmp/ai-doc-generator
```

### 5.4 Rimuovi i file temporanei di download

Su PowerShell:

```powershell
Remove-Item docgen.zip -Force
Remove-Item docgen_tmp -Recurse -Force
```

In alternativa (bash/sh):

```bash
rm -f docgen.zip
rm -rf docgen_tmp
```

### 5.5 Verifica post-installazione

Controlla di nuovo:

```bash
python3 -c "import docgen; print(docgen.__version__)"
```

Fallback:

```bash
python -c "import docgen; print(docgen.__version__)"
```

Se la verifica fallisce, interrompi il workflow e segnala errore.

---

## Step 6 — Esecuzione DocGen

Dopo esserti assicurato che DocGen sia installato e aggiornato, esegui:

```bash
python3 -m docgen . --agent-export -n "<nome_progetto>"
```

Fallback:

```bash
python -m docgen . --agent-export -n "<nome_progetto>"
```

Se l'utente non fornisce il nome progetto, usa il nome della cartella workspace come default ragionevole.

---

## Step 7 — Verifica output agent-export

DocGen produce file diversi in base al tipo di progetto:

**Progetto singolo** (un solo modulo rilevato):
- deve esistere `DocGen/docgen_context.md`

**Progetto multi-microservizio** (più moduli rilevati):
- deve esistere `DocGen/docgen_instructions.md`
- deve esistere almeno un file `DocGen/docgen_context_*.md`

Se nessuno di questi file esiste, interrompi il workflow e segnala che l'export DocGen non è riuscito correttamente.

Conserva mentalmente il tipo di progetto rilevato (singolo o multi) — ti servirà nello Step 8.

---

## Step 8 — Generazione documentazione

**Progetto singolo** (rilevato nello Step 7):
1. Leggi `DocGen/docgen_context.md`.
2. Segui ESATTAMENTE il piano di lavoro descritto nel file.
3. Leggi i file sorgente indicati nel contesto, rispettando la priorità:
   - 🔴 Obbligatori: leggili SEMPRE
   - 🟡 Importanti: leggili se servono dettagli su entità, configurazioni o regole di business
   - ⚪ Supporto: leggili solo se hai bisogno di contesto aggiuntivo
4. Genera tutti i documenti Markdown previsti seguendo la struttura indicata nel file di contesto.
5. Salva gli output nella cartella `DocGen/`.

**Progetto multi-microservizio** (rilevato nello Step 7):
1. Leggi `DocGen/docgen_instructions.md`.
2. Segui ESATTAMENTE il piano di lavoro descritto nel file.
3. Per ogni microservizio, leggi il relativo `DocGen/docgen_context_<nome>.md`.
4. Genera tutti i documenti Markdown previsti (per-servizio + documenti d'insieme).
5. Salva gli output nelle cartelle indicate da DocGen.

### Regole di qualità per la generazione

- **Sezioni senza dati**: quando non hai informazioni sufficienti per una sezione, scrivi:
  `> ⚠️ Da completare — informazioni non rilevabili dal codice sorgente in questa fase.`
  NON inventare contenuto.

- **File da leggere — priorità**:
  - 🔴 Obbligatori (controller, service, business_critical): leggili SEMPRE — contengono logica principale, API, regole di business
  - 🟡 Importanti (entity, repository, config, dto, **app_config**, build_config, package_config): leggili per dettagli su entità, configurazioni e dipendenze
    - **I file `app_config` (application.yml, appsettings.json) vanno letti SEMPRE**: contengono porte di servizio, URL di sistemi esterni, SLA e configurazioni operative fondamentali
  - ⚪ Supporto (test, utility, stili): leggili solo se serve contesto aggiuntivo

- **Dati di dominio — sezione critica**: cerca attivamente file con `Enum`, `Constant`, `Status`, `Type`, `Code` nel nome. Contengono i valori di dominio reali (es. tipi di ricorso con codici, stati con transizioni) che devono essere documentati nella sezione "Dati di dominio" della Specifica Funzionale.

- **Revisione finale obbligatoria**: dopo aver completato tutti i documenti, esegui una revisione:
  1. Torna su ogni sezione marcata `⚠️ Da completare` e verifica se hai trovato le informazioni leggendo altri file del progetto. Se sì, completa la sezione.
  2. Verifica la coerenza tra Specifica Funzionale e Specifica Tecnica (endpoint API↔casi d'uso, entità ER↔modello funzionale, ruoli↔attori).
  3. Per i progetti multi-microservizio, verifica che l'Architettura di Sistema sia coerente con le specifiche per-servizio (matrice dipendenze↔endpoint, ER sistema↔entità per-servizio).
  4. Controlla la sintassi Mermaid di tutti i diagrammi.

- **Diagrammi Mermaid**: ogni documento deve includere i diagrammi previsti dalla struttura. Usa sempre sintassi standard e verifica che siano renderizzabili.

- **Non saltare sezioni**: anche se una sezione ha solo il marker `⚠️ Da completare`, includila nel documento — serve come traccia per completamento futuro.

---

## Step 9 — Cleanup (DEFAULT: TRUE)

Esegui cleanup automaticamente, salvo richiesta esplicita contraria dell'utente:

```bash
python3 -m docgen --cleanup DocGen/
```

Fallback:

```bash
python -m docgen --cleanup DocGen/
```

---

## Step 10 — Render DOCX (DEFAULT: FALSE)

Esegui render solo se l'utente lo richiede esplicitamente, ad esempio con `--render`.

Comando:

```bash
python3 -m docgen --render DocGen/*.md --meta PROGETTO="<nome_progetto>"
```

Fallback:

```bash
python -m docgen --render DocGen/*.md --meta PROGETTO="<nome_progetto>"
```

IMPORTANTE:
- il cleanup viene prima del render, come richiesto;
- il render NON è automatico di default.

---

## Regole operative

- NON saltare step.
- NON usare una versione locale non verificata di DocGen.
- Se `docgen` manca o è obsoleto, installa/aggiorna SEMPRE dalla latest release GitHub.
- Rispetta i template e la struttura documentale generata da DocGen.
- Leggi sempre i file di contesto prima di generare i documenti.
- Usa `python3` quando disponibile; in caso contrario usa `python`.
- Cleanup di default: attivo.
- Render di default: disattivo.
- Non inventare contenuto: usa il marker `⚠️ Da completare` per le sezioni senza dati.
- Esegui sempre la revisione finale dopo aver generato tutti i documenti.

---

## Esempi di utilizzo

- `/docgen-documentation`
- `/docgen-documentation NomeProgetto`
- `/docgen-documentation NomeProgetto --render`
- `/docgen-documentation NomeProgetto --no-cleanup`
