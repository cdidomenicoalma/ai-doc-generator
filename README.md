# DocGen — Generatore Automatico di Documentazione da Codebase

**DocGen** analizza il codice sorgente di un progetto software e genera automaticamente 
documentazione professionale in italiano:

- **Specifica Funzionale** — requisiti, casi d'uso, flussi operativi, modello dati, regole di business
- **Specifica Tecnica** — architettura, API REST, schema DB, diagrammi Mermaid, stack tecnologico, gestione errori
- **Architettura di Sistema** — integrazioni tra microservizi, flussi end-to-end (solo progetti multi-servizio)

Output in formato **Markdown** e **Word (.docx)**.

---

## Indice

1. [Requisiti](#1-requisiti)
2. [Installazione](#2-installazione)
3. [Come si usa](#3-come-si-usa)
4. [Linguaggi supportati](#4-linguaggi-supportati)
5. [Cosa succede quando lo lancio](#5-cosa-succede-quando-lo-lancio)
6. [Output generato](#6-output-generato)
7. [Provalo con il progetto di esempio](#7-provalo-con-il-progetto-di-esempio)
8. [Riferimento opzioni CLI](#8-riferimento-opzioni-cli)
9. [Domande frequenti](#9-domande-frequenti)
10. [Stima costi API](#10-stima-costi-api)
11. [Per sviluppatori](#11-per-sviluppatori)

---

## 1. Requisiti

| Cosa | Dettaglio |
|------|-----------|
| **Python** | 3.9 o superiore (`python3 --version`) |
| **API Key Anthropic** | Solo per modalità API diretta. Si ottiene su [console.anthropic.com](https://console.anthropic.com/) |

Non serve installare Java, Node.js o .NET: DocGen legge il codice ma non lo esegue.

---

## 2. Installazione

```bash
cd ai-doc-generator
pip3 install -e .
```

Verifica:
```bash
python3 -m docgen --help
```

---

## 3. Come si usa

DocGen ha **3 modalità**:

### 3.1 — Dry Run (anteprima gratuita)

Analizza il progetto senza chiamare API. Mostra statistiche, classificazione file, endpoint rilevati, stima costi.

```bash
python3 -m docgen /percorso/progetto --dry-run -n "Nome Progetto"
```

### 3.2 — Agent Export ⭐ Consigliata

Genera un pacchetto di contesto strutturato che un agente AI (GitHub Copilot, Kilo Code, Claude Code) può usare per generare la documentazione leggendo i file dal workspace. Nessuna API key necessaria.

```bash
python3 -m docgen /percorso/progetto --agent-export -n "Nome Progetto"
```

Produce (nella cartella `<progetto>/DocGen/`):
- **Progetto singolo**: `docgen_context.md` + `docgen_files.json` + `docgen_index.md`
- **Multi-microservizio**: `docgen_instructions.md` + `docgen_context_<modulo>.md` per servizio + `docgen_files.json` + `docgen_index.md`

**Come usare:**
1. Lancia il comando
2. Apri VS Code sul progetto
3. Passa `docgen_context.md` (o `docgen_instructions.md`) all'agente
4. L'agente legge i file sorgente e genera la documentazione in `.md`
5. Converti in Word con template aziendale: `python3 -m docgen --render DocGen/*.md`
6. Pulisci i file temporanei: `python3 -m docgen --cleanup DocGen/`

I file sono raggruppati per urgenza: 🔴 obbligatori, 🟡 importanti, ⚪ supporto.

### 3.3 — API Diretta (generazione automatica)

Genera i documenti chiamando direttamente Claude. Richiede API key, comporta costi.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m docgen /percorso/progetto -n "Nome Progetto"
```

Per progetti grandi (3+ microservizi), DocGen chiede se generare documentazione per-servizio o unificata.

### 3.4 — Conversione DOCX con template aziendale

Converte i file `.md` generati dall'agente in `.docx` con formattazione aziendale (copertina, intestazione, piè di pagina, stili Word).

```bash
python3 -m docgen --render DocGen/*.md --meta PROGETTO="Nome Progetto" CLIENTE="Nome Cliente"
```

Il template aziendale include:
- **Copertina** con tabella titolo e metadati (cliente, progetto, data, versione, redatto da, ecc.)
- **Header** su ogni pagina (ente, progetto, tipo documento, versione, data)
- **Footer** su ogni pagina (nome documento + numerazione pagine)
- **Stili** Heading 1/2/3 e Normal coerenti con il format aziendale

I metadati della copertina si personalizzano con `--meta`:

| Chiave | Default | Esempio |
|--------|---------|---------|
| `INTESTAZIONE_ENTE` | XXXX | `"MINISTERO DELLA DIFESA"` |
| `CLIENTE` | XXXX | `"Nome Cliente"` |
| `PROGETTO` | XXXX | `"Nome Progetto"` |
| `REDATTO_DA` | DocGen (generazione automatica) | `"Mario Rossi"` |
| `VERSIONE` | 1.0 | `"2.0"` |
| `STATO` | Bozza | `"Approvato"` |

Per usare un template diverso: `--template /percorso/template.docx`

### 3.5 — Pulizia file temporanei

Rimuove i file di contesto dell'agent-export, lasciando solo i documenti finali `.md` e `.docx`.

```bash
python3 -m docgen --cleanup DocGen/
```

File rimossi: `analisi_statica.md`, `struttura_progetto.txt`, `docgen_context*.md`, `docgen_files.json`, `docgen_index.md`, `docgen_instructions.md`.

---

## 4. Linguaggi supportati

| Linguaggio | Framework | Cosa rileva |
|---|---|---|
| **Java** | Spring Boot, JPA/Hibernate | Controller, Service, Entity, Repository, endpoint REST, campi JPA, dipendenze Maven |
| **C#** | ASP.NET Core, EF Core, Razor | Controller `[ApiController]`, DbContext, Entity `[Table]`/`[Key]`, dipendenze NuGet, `appsettings.json` |
| **TypeScript/JS** | Angular, NestJS, Express | Componenti, servizi, routing (eager + lazy), moduli, dipendenze NPM |
| **Python** | FastAPI, Flask, Django | Endpoint, modelli, dipendenze |
| **Altro** | Go, Rust, Ruby, PHP | Estrazione dipendenze base |

Anche per stack non elencati, DocGen legge il codice sorgente e l'AI produce documentazione basandosi su quello che trova.

---

## 5. Cosa succede quando lo lancio

4 fasi automatiche:

1. **Scansione** — Trova i file sorgente, ignora `node_modules`, `target`, `bin`, `obj`, `.git`, `wwwroot`, ecc. Classifica ogni file per categoria e urgenza.

2. **Analisi statica** — Estrae endpoint REST, entità DB, route frontend, componenti, dipendenze, configurazione database. Tutto senza eseguire il codice.

3. **Pianificazione** — Raggruppa i file in chunk per modulo. Rileva automaticamente i microservizi.

4. **Generazione** — (Solo API diretta) Invia i chunk a Claude e produce i documenti. Con `--agent-export`, genera il pacchetto di contesto e si ferma.

---

## 6. Output generato

Output in `<progetto>/DocGen/`:

| File | Presente in |
|------|-------------|
| `struttura_progetto.txt` | Sempre |
| `analisi_statica.md` | Sempre |
| `docgen_context.md` / `docgen_instructions.md` | `--agent-export` |
| `docgen_context_<modulo>.md` | `--agent-export` multi-servizio |
| `docgen_files.json` | `--agent-export` |
| `docgen_index.md` | `--agent-export` |
| `specifica_funzionale.md` / `.docx` | API diretta |
| `specifica_tecnica.md` / `.docx` | API diretta |
| `architettura_sistema.md` / `.docx` | API diretta multi-servizio |

---

## 7. Provalo con il progetto di esempio

```bash
# Anteprima
python3 -m docgen ./test-project --dry-run -n "Gestione Utenti PA"

# Agent export
python3 -m docgen ./test-project --agent-export -n "Gestione Utenti PA"

# Generazione (richiede API key)
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m docgen ./test-project -n "Gestione Utenti PA"
```

---

## 8. Riferimento opzioni CLI

| Opzione | Default | Descrizione |
|---------|---------|-------------|
| `project_path` | *(obbligatorio)* | Cartella del progetto da analizzare |
| `-n`, `--name` | nome cartella | Nome progetto (appare nei documenti) |
| `-o`, `--output` | `<progetto>/DocGen` | Cartella output |
| `-f`, `--format` | `all` | Formato: `all`, `md`, `docx` |
| `-d`, `--dry-run` | — | Solo anteprima, nessuna API |
| `--agent-export` | — | Esporta contesto per agenti AI |
| `--render FILE ...` | — | Converte `.md` in `.docx` con template aziendale |
| `--template PATH` | `templates/template_aziendale.docx` | Template `.docx` personalizzato |
| `--cleanup [DIR]` | — | Rimuove file temporanei dell'agent-export |
| `--meta KEY=VALUE ...` | — | Metadati copertina (es. `CLIENTE="Acme"`) |
| `-m`, `--model` | `claude-sonnet-4-20250514` | Modello Claude |
| `--chunk-budget` | 80000 | Token per chunk |
| `--max-tokens` | 200000 | Limite contesto modello |

---

## 9. Domande frequenti

### Quanto costa una generazione?

Usa `--dry-run` per la stima. Ordine di grandezza:

| Dimensione | Costo stimato |
|---|---|
| Piccolo (~10 file) | < $0.10 |
| Medio (~100 file) | $0.20 – $0.50 |
| Grande (~500 file) | $0.50 – $2.00 |
| Enterprise (~2000 file) | $2.00 – $5.00 |

### Il dry-run e l'agent-export costano qualcosa?

**No.** Nessuna chiamata API. Completamente gratuiti e locali.

### Funziona con .NET 8 + Angular?

**Sì.** Rileva controller ASP.NET Core (`[ApiController]`, `[HttpGet]`/`[HttpPost]`/...), entità EF Core (`[Table]`, `[Key]`, `DbSet<>`), dipendenze NuGet da `.csproj`, configurazione da `appsettings.json`. Per Angular: componenti, servizi, routing, moduli, dipendenze NPM.

### I miei dati vengono inviati da qualche parte?

In modalità API diretta, il codice viene inviato all'API di Anthropic (Claude). In `--dry-run` e `--agent-export` **non viene inviato nulla**. Verifica le policy Anthropic per vincoli di riservatezza.

### Cosa succede se un file è troppo grande?

File oltre 500KB vengono saltati. File grandi vengono troncati con limiti adattivi per categoria: 80K caratteri per file business-critical/service/controller, 40K per il resto.

---

## 10. Stima costi API

| | Prezzo |
|---|--------|
| Token input | $3 / milione di token |
| Token output | $15 / milione di token |

La stima viene mostrata nel dry-run e durante la generazione.

---

## 11. Per sviluppatori

### Struttura del codice

```
docgen/
├── main.py               # CLI e orchestrazione
├── config.py             # Configurazione centralizzata
├── scanner.py            # Scansione filesystem e classificazione file
├── analyzer.py           # Estrazione statica (endpoint, entità, route, dipendenze)
├── chunker.py            # Raggruppamento file per modulo con budget token
├── generator.py          # Chiamate Claude API con retry
├── prompts.py            # Template prompt in italiano
├── renderer.py           # Conversione Markdown → DOCX (stile interno)
└── template_renderer.py  # Conversione Markdown → DOCX con template aziendale

templates/
├── template_aziendale.docx  # Template Word con placeholder
└── build_template.py        # Script per ricostruire il template

tests/
└── test_docgen.py   # 181 test automatici

test-project/        # Progetto di esempio Spring Boot + Angular
```

### Test

```bash
python3 -m pytest tests/ -v
```

---

## Licenza

Uso interno — Almaviva SpA
