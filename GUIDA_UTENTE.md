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
| C# | ASP.NET Core, Entity Framework Core, Razor |
| TypeScript/JS | Angular, NestJS, Express.js |
| Python | FastAPI, Flask, Django |
| Altro | Go, Rust, Ruby, PHP (estrazione dipendenze) |

### Come funziona in breve

1. **Scansione** — legge tutti i file sorgente del progetto
2. **Classificazione** — classifica ogni file per categoria (controller, service, entity, business_critical, ecc.) e urgenza (🔴 obbligatorio, 🟡 importante, ⚪ supporto)
3. **Analisi statica** — estrae endpoint REST, entità/modelli, route frontend, dipendenze, configurazione DB
4. **Generazione** — produce i documenti tramite un LLM (API Claude) o un agente AI (Copilot, Kilo Code, Claude Code)

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

DocGen offre **3 modalità** di funzionamento.

---

### 4.1 Modalità Dry Run (`--dry-run`)

**Scopo**: analizza il progetto SENZA generare documenti. Utile per verificare che la scansione e la classificazione funzionino correttamente prima di procedere.

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

**Cosa produce (progetto singolo)** — nella cartella `<progetto>/DocGen/`:
- `docgen_context.md` — contesto completo: struttura progetto, analisi statica, file classificati per urgenza, istruzioni operative per l'agente, template dei documenti
- `docgen_files.json` — stessi dati in formato JSON machine-readable
- `docgen_index.md` — indice dei file generati

**Cosa produce (progetto multi-microservizio)** — nella cartella `<progetto>/DocGen/`:
- `docgen_instructions.md` — istruzioni generali + template dei documenti
- `docgen_context_<modulo>.md` — un file di contesto per ogni microservizio, con i file classificati per urgenza (🔴/🟡/⚪)
- `docgen_files.json` — dati machine-readable
- `docgen_index.md` — indice dei file generati

**Costo**: zero (nessuna chiamata API — è l'agente che fa il lavoro).

**Come usarla (passo passo) — progetto singolo:**

1. Lancia il comando:

   ```bash
   python3 -m docgen /percorso/al/progetto --agent-export -n "Nome Progetto"
   ```

2. Apri il progetto in VS Code (se non lo hai già aperto)

3. Apri la chat dell'agente (Copilot, Kilo Code, ecc.) e scrivi:

   > Leggi il file `DocGen/docgen_context.md` e segui le istruzioni contenute per generare la documentazione. Salva i documenti nella cartella `DocGen/`.

4. L'agente leggerà il contesto, poi leggerà i file sorgente dal workspace e genererà i documenti

5. Converti i `.md` in `.docx` con template aziendale:

   ```bash
   python3 -m docgen --render DocGen/*.md --meta PROGETTO="Nome Progetto"
   ```

6. Rimuovi i file temporanei:

   ```bash
   python3 -m docgen --cleanup DocGen/
   ```

**Come usarla (passo passo) — progetto multi-microservizio:**

1. Lancia il comando (DocGen rileva automaticamente i microservizi):

   ```bash
   python3 -m docgen /percorso/al/progetto --agent-export -n "Nome Progetto"
   ```

2. Apri il progetto in VS Code

3. Apri la chat dell'agente e scrivi:

   > Leggi il file `DocGen/docgen_instructions.md` e segui le istruzioni. Per ogni microservizio, leggi il relativo `docgen_context_<nome>.md`. Salva i documenti nella cartella `DocGen/`.

4. L'agente procederà un microservizio alla volta, poi genererà i documenti d'insieme (architettura, funzionale completa, tecnica completa)

5. Converti i `.md` in `.docx` con template aziendale:

   ```bash
   python3 -m docgen --render DocGen/*.md --meta PROGETTO="Nome Progetto" CLIENTE="Nome Cliente"
   ```

6. Rimuovi i file temporanei:

   ```bash
   python3 -m docgen --cleanup DocGen/
   ```

**Classificazione dei file per urgenza:**

I file nei contesti sono raggruppati per urgenza visiva:
- 🔴 **Obbligatori** — controller, service, business_critical → leggere SEMPRE
- 🟡 **Importanti** — entity, repository, config, DTO → leggere se servono dettagli
- ⚪ **Supporto** — test, utility, stili → leggere solo se serve contesto aggiuntivo

**Vantaggi rispetto alla modalità API diretta:**
- L'agente legge i file dal filesystem → nessun copia-incolla di codice nei prompt
- Risparmio del 70-80% di token rispetto alla modalità API diretta
- L'agente ha accesso all'intero progetto, non solo ai chunk selezionati

---

### 4.3 Modalità API Diretta (default)

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

### 4.4 Conversione DOCX con template aziendale (`--render`)

**Scopo**: converte i file `.md` generati dall'agente (o manualmente) in documenti Word (`.docx`) con formattazione aziendale: copertina, intestazione, piè di pagina, stili Word.

**Comando:**

```bash
python3 -m docgen --render DocGen/*.md --meta PROGETTO="Nome Progetto" CLIENTE="Nome Cliente"
```

**Cosa fa:**
- Apre il template aziendale (`templates/template_aziendale.docx`)
- Sostituisce i placeholder della copertina con i metadati forniti tramite `--meta`
- Parsa il Markdown e lo inserisce nel documento con gli stili Word del template
- Genera un file `.docx` per ogni `.md` fornito

**Metadati personalizzabili (`--meta`):**

| Chiave | Default | Descrizione |
|--------|---------|-------------|
| `INTESTAZIONE_ENTE` | XXXX | Intestazione ente nella copertina e header |
| `CLIENTE` | XXXX | Nome cliente |
| `PROGETTO` | XXXX | Nome progetto |
| `REDATTO_DA` | DocGen (generazione automatica) | Autore del documento |
| `APPROVATO_DA` | XXXX | Approvatore |
| `VERIFICATO_DA` | XXXX | Verificatore |
| `VERSIONE` | 1.0 | Versione del documento |
| `STATO` | Bozza | Stato del documento |

I campi `NOME_DOCUMENTO`, `TIPO_DOCUMENTO` e `DATA` vengono compilati automaticamente dal nome del file e dalla data corrente.

**Template personalizzato**: per usare un template `.docx` diverso da quello incluso:

```bash
python3 -m docgen --render *.md --template /percorso/mio_template.docx
```

---

### 4.5 Pulizia file temporanei (`--cleanup`)

**Scopo**: rimuove i file di contesto generati dall'agent-export, lasciando solo i documenti finali `.md` e `.docx`.

**Comando:**

```bash
python3 -m docgen --cleanup DocGen/
```

**File rimossi:**
- `analisi_statica.md`
- `struttura_progetto.txt`
- `docgen_context.md` / `docgen_context_*.md`
- `docgen_files.json`
- `docgen_index.md`
- `docgen_instructions.md`

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
| `--render FILE ...` | — | Converte `.md` in `.docx` con template aziendale |
| `--template PATH` | `templates/template_aziendale.docx` | Template `.docx` personalizzato |
| `--cleanup [DIR]` | — | Rimuove file temporanei dell'agent-export |
| `--meta KEY=VALUE ...` | — | Metadati copertina (es. `CLIENTE="Acme"`) |
| `--chunk-budget` | 80000 | Token massimi per chunk |
| `--max-tokens` | 200000 | Token massimi contesto modello |

---

## 6. Struttura output

### Progetto singolo

```
<progetto>/DocGen/
├── struttura_progetto.txt
├── analisi_statica.md
├── docgen_context.md           ← (solo con --agent-export)
├── docgen_files.json           ← (solo con --agent-export)
├── docgen_index.md             ← (solo con --agent-export)
├── specifica_funzionale.md     ← (solo con API diretta)
├── specifica_funzionale.docx
├── specifica_tecnica.md
└── specifica_tecnica.docx
```

### Progetto multi-microservizio — Agent Export

```
<progetto>/DocGen/
├── struttura_progetto.txt
├── analisi_statica.md
├── docgen_instructions.md
├── docgen_context_<servizio-1>.md
├── docgen_context_<servizio-2>.md
├── ...
├── docgen_files.json
└── docgen_index.md
```

### Progetto multi-microservizio — API Diretta

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
   > Leggi `DocGen/docgen_context.md` (o `DocGen/docgen_instructions.md` per multi-servizio) e segui le istruzioni per generare la documentazione.

4. **Conversione DOCX** — converti i documenti generati in formato Word con template aziendale:
   ```bash
   python3 -m docgen --render DocGen/*.md --meta PROGETTO="Nome" CLIENTE="Nome Cliente"
   ```

5. **Pulizia** — rimuovi i file temporanei:
   ```bash
   python3 -m docgen --cleanup DocGen/
   ```

6. **Revisione** — controlla i documenti generati e correggi eventuali imprecisioni.

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
Per la modalità `--agent-export` e `--dry-run` NON serve alcuna API key.

### "Nessun file sorgente trovato"
Il progetto non contiene file con estensioni supportate, oppure tutti i file sono in directory ignorate (node_modules, target, bin, obj, .git, ecc.).

### Il progetto è troppo grande
Riduci il `--chunk-budget` per creare più chunk più piccoli, oppure usa `--agent-export` che non ha limiti di token.

### L'agente non legge tutti i file
Con `--agent-export`, i file sono raggruppati per urgenza (🔴/🟡/⚪). Chiedi esplicitamente all'agente di leggere i file 🔴 (obbligatori) e business_critical.
