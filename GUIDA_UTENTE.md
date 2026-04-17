# DocGen — Guida Utente

## 1. Cos'è DocGen

DocGen è uno strumento da riga di comando (CLI) che analizza automaticamente il codice sorgente di un progetto software e genera documentazione professionale.

### Cosa produce

- **Specifica Funzionale** — requisiti funzionali, casi d'uso, modello dati, regole di business
- **Specifica Tecnica** — architettura, stack tecnologico, API REST, modello dati tecnico, flussi asincroni, gestione errori
- **Documento di Architettura di Sistema** — generato solo per progetti multi-microservizio, descrive le integrazioni tra i servizi

I documenti vengono generati in formato **Markdown** e/o **DOCX** (Word).

### Linguaggi e framework supportati

| Linguaggio | Framework rilevati |
|---|---|
| Java | Spring Boot, Spring Security, JPA/Hibernate |
| C# | ASP.NET Core, Entity Framework Core |
| TypeScript/JS | Angular, NestJS, Express.js |
| Python | FastAPI, Flask, Django |
| Altro | Go, Rust, Ruby, PHP (estrazione dipendenze) |

### Come funziona in breve

1. **Scansione** — legge tutti i file sorgente del progetto
2. **Classificazione** — classifica ogni file per categoria (controller, service, entity, business_critical, ecc.) e priorità (alta, media, bassa)
3. **Analisi statica** — estrae endpoint REST, entità/modelli, route frontend, dipendenze, configurazione DB
4. **Generazione** — usa un LLM (Large Language Model) per produrre i documenti a partire dal codice e dall'analisi

---

## 2. Requisiti di sistema

### Software necessario

| Requisito | Versione minima |
|---|---|
| **Python** | 3.9 o superiore |
| **pip** | qualsiasi versione |

### Verifica Python

```bash
python3 --version
# deve mostrare Python 3.9 o superiore
```

### Dipendenze Python (installate automaticamente)

- `anthropic` — client API Claude (necessario solo per modalità API diretta)
- `python-docx` — generazione file DOCX
- `rich` — output formattato nel terminale
- `pyyaml` — parsing file di configurazione YAML

---

## 3. Installazione

### Passo 1: Scaricare il progetto

Copia la cartella `ai-doc-generator` in una posizione a tua scelta sul computer.

### Passo 2: Installare DocGen

Apri un terminale e lancia:

```bash
pip3 install -e "/percorso/completo/alla/cartella/ai-doc-generator"
```

**Esempio concreto:**

```bash
pip3 install -e "/Users/carlodidomenico/Library/CloudStorage/OneDrive-AlmavivaSpA/Progetti/ai-doc-generator"
```

> **Nota**: il flag `-e` installa in modalità "editable" — se il codice di DocGen viene aggiornato, le modifiche sono immediatamente disponibili senza reinstallare.

### Passo 3: Verifica installazione

```bash
python3 -m docgen --help
```

Se mostra l'help con le opzioni disponibili, l'installazione è riuscita.

---

## 4. Modalità di utilizzo

DocGen offre **5 modalità** di funzionamento, dalla più semplice alla più avanzata.

---

### 4.1 Modalità Dry Run (`--dry-run`)

**Scopo**: analizza il progetto SENZA generare documenti. Utile per verificare che la scansione e la classificazione funzionino correttamente prima di investire token/costi.

**Comando:**

```bash
python3 -m docgen /percorso/al/progetto --dry-run -n "Nome Progetto"
```

**Cosa produce:**
- Statistiche nel terminale (file trovati, moduli, endpoint, entità, ecc.)
- Piano dei chunk (come verrebbero divisi i file per l'analisi)
- Stima costo API
- File nella cartella `<progetto>/DocGen/`:
  - `struttura_progetto.txt` — albero dei file classificati
  - `analisi_statica.md` — riepilogo endpoint, entità, dipendenze

**Costo**: zero (nessuna chiamata API).

**Quando usarla**: sempre come primo passo, per verificare che DocGen riconosca correttamente il progetto.

---

### 4.2 Modalità Agent Export (`--agent-export`) ⭐ Consigliata

**Scopo**: genera un pacchetto informativo strutturato che un agente AI (GitHub Copilot, Kilo Code, Claude Code) può usare per generare la documentazione leggendo i file direttamente dal workspace.

**Comando:**

```bash
python3 -m docgen /percorso/al/progetto --agent-export -n "Nome Progetto"
```

**Cosa produce** (nella cartella `<progetto>/DocGen/`):
- `docgen_context.md` — contesto completo: struttura progetto, analisi statica, file classificati per priorità, istruzioni operative per l'agente, template dei documenti da generare
- `docgen_files.json` — stessi dati in formato JSON machine-readable

**Costo**: zero (nessuna chiamata API — è l'agente che fa il lavoro).

**Come usarla (passo passo):**

1. Apri il terminale nella root del progetto da analizzare:

   ```bash
   cd /percorso/al/progetto
   python3 -m docgen . --agent-export -n "Nome Progetto"
   ```

2. Apri il progetto in VS Code (se non lo hai già aperto)

3. Apri la chat dell'agente (Copilot, Kilo Code, ecc.) e scrivi:

   > Leggi il file `DocGen/docgen_context.md` e segui le istruzioni contenute per generare la documentazione. Salva i documenti nella cartella `DocGen/`.

4. L'agente leggerà il contesto, poi leggerà i file sorgente dal workspace e genererà i documenti

**Vantaggi rispetto alle altre modalità:**
- L'agente legge i file dal filesystem → nessun copia-incolla di codice nei prompt
- Risparmio del 70-80% di token rispetto alla modalità API diretta
- L'agente ha accesso all'intero progetto, non solo ai chunk selezionati

---

### 4.3 Modalità Export Prompt (`--export-prompts`)

**Scopo**: genera i prompt pronti da copiare-incollare manualmente in qualsiasi LLM (ChatGPT, Claude web, Gemini, ecc.).

**Comando:**

```bash
python3 -m docgen /percorso/al/progetto --export-prompts -n "Nome Progetto"
```

**Cosa produce** (nella cartella `<progetto>/DocGen/prompts/`):
- `00_SYSTEM_PROMPT.md` — prompt di sistema
- `01_ANALISI_CHUNK_01_<modulo>.md`, `01_ANALISI_CHUNK_02_<modulo>.md`, ... — un prompt per ogni chunk di codice
- `02_SPECIFICA_FUNZIONALE.md` — prompt per generare il documento funzionale
- `03_SPECIFICA_TECNICA.md` — prompt per generare il documento tecnico

Per progetti multi-microservizio, vengono create sottocartelle per ogni servizio + un prompt `ARCHITETTURA_SISTEMA.md`.

**Costo**: zero (nessuna chiamata API).

**Come usarla:**

1. Lancia il comando
2. Apri un LLM a scelta (ChatGPT, Claude, ecc.)
3. Incolla `00_SYSTEM_PROMPT.md` come system prompt
4. Invia i prompt `01_ANALISI_CHUNK_*.md` uno alla volta e raccogli le risposte
5. Incolla le risposte nei placeholder dei prompt `02_SPECIFICA_FUNZIONALE.md` e `03_SPECIFICA_TECNICA.md`

---

### 4.4 Modalità LLM Bridge (`--llm-bridge`)

**Scopo**: scambio automatizzato prompt/risposta via filesystem. Lo script scrive i prompt come file, un agente esterno (Kilo Code) li legge, processa col suo LLM e scrive le risposte.

**Comando:**

```bash
python3 -m docgen /percorso/al/progetto --llm-bridge -n "Nome Progetto"
```

**Costo**: dipende dall'agente usato (Kilo Code usa i suoi token/crediti).

**Come funziona:**
1. Lo script crea una cartella `.bridge/` dentro la directory di output
2. Scrive un prompt (`prompt_001.md`) e un flag (`READY`)
3. L'agente esterno rileva il flag, legge il prompt, genera la risposta e la salva (`response_001.md`)
4. Lo script rileva la risposta, procede al prompt successivo
5. Alla fine genera i documenti finali

> **Nota**: questa modalità richiede che l'agente esterno sia configurato per monitorare la cartella `.bridge/`.

---

### 4.5 Modalità API Diretta (default)

**Scopo**: genera i documenti chiamando direttamente l'API di Claude (Anthropic). Completamente automatico, ma richiede una API key e comporta costi.

**Prerequisito:**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**Comando:**

```bash
python3 -m docgen /percorso/al/progetto -n "Nome Progetto"
```

**Costo**: variabile in base alla dimensione del progetto. Stimato in fase di analisi (mostrato nel terminale). Tipicamente $0.50–$5.00 per progetto.

**Come funziona:**
1. Scansiona e analizza il progetto
2. Per progetti grandi (3+ moduli, 8+ chunk), chiede se generare documentazione per-microservizio o unificata
3. Chiama l'API di Claude per ogni chunk + documenti di sintesi
4. Salva i documenti in formato Markdown e/o DOCX

---

## 5. Opzioni CLI complete

| Opzione | Default | Descrizione |
|---|---|---|
| `project_path` | *(obbligatorio)* | Path al progetto da analizzare. Usa `.` per la directory corrente |
| `-n`, `--name` | nome della cartella | Nome del progetto (compare nei documenti) |
| `-o`, `--output` | `<progetto>/DocGen` | Directory dove salvare l'output |
| `-f`, `--format` | `all` | Formato output: `all` (MD+DOCX), `md`, `docx` |
| `-m`, `--model` | `claude-sonnet-4-20250514` | Modello Claude (solo per modalità API) |
| `-d`, `--dry-run` | — | Solo analisi, nessuna generazione |
| `--agent-export` | — | Esporta contesto per agenti AI |
| `--export-prompts` | — | Esporta prompt come file Markdown |
| `--llm-bridge` | — | Modalità bridge con agente esterno |
| `--chunk-budget` | 120000 | Token massimi per chunk |
| `--max-tokens` | 200000 | Token massimi contesto modello |

---

## 6. Struttura output

### Progetto singolo

```
<progetto>/DocGen/
├── struttura_progetto.txt
├── analisi_statica.md
├── docgen_context.md          ← (solo con --agent-export)
├── docgen_files.json           ← (solo con --agent-export)
├── specifica_funzionale.md
├── specifica_funzionale.docx
├── specifica_tecnica.md
└── specifica_tecnica.docx
```

### Progetto multi-microservizio

```
<progetto>/DocGen/
├── struttura_progetto.txt
├── analisi_statica.md
├── architettura_sistema.md
├── architettura_sistema.docx
├── <microservizio-1>/
│   ├── specifica_funzionale.md
│   ├── specifica_funzionale.docx
│   ├── specifica_tecnica.md
│   └── specifica_tecnica.docx
├── <microservizio-2>/
│   └── ...
└── ...
```

---

## 7. Workflow consigliato

1. **Dry run** — verifica che il progetto venga scansionato correttamente:
   ```bash
   python3 -m docgen /percorso/progetto --dry-run -n "Nome"
   ```

2. **Agent export** — genera il contesto per l'agente:
   ```bash
   python3 -m docgen /percorso/progetto --agent-export -n "Nome"
   ```

3. **Generazione** — apri VS Code sul progetto e dai all'agente:
   > Leggi `DocGen/docgen_context.md` e segui le istruzioni per generare la documentazione.

4. **Revisione** — controlla i documenti generati e correggi eventuali imprecisioni.

---

## 8. Risoluzione problemi

### "No module named docgen"
DocGen non è installato. Lancia:
```bash
pip3 install -e "/percorso/a/ai-doc-generator"
```

### "ANTHROPIC_API_KEY non configurata"
Serve solo per la modalità API diretta (senza flag). Imposta:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### "Nessun file sorgente trovato"
Il progetto non contiene file con estensioni supportate, oppure tutti i file sono in directory ignorate (node_modules, target, .git, ecc.).

### Il progetto è troppo grande
Riduci il `--chunk-budget` per creare più chunk più piccoli, oppure usa `--agent-export` che non ha limiti di token.

### L'agente non legge tutti i file
Con `--agent-export`, il file `docgen_context.md` elenca i file per priorità. Chiedi esplicitamente all'agente di leggere i file con priorità ALTA e business_critical.
