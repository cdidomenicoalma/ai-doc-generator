# DocGen — Generatore Automatico di Documentazione da Codebase

**DocGen** analizza il codice sorgente di un progetto software e genera automaticamente documentazione professionale in italiano, conforme agli standard IEEE 830 (SRS), IEEE 1016 (SDD) e arc42:

- **Specifica Funzionale** — requisiti, casi d'uso, dati di dominio (enum/stati/codici), regole di business, matrici CRUD e funzionalità-componenti
- **Specifica Tecnica** — architettura, API REST, schema DB, diagrammi Mermaid, stack tecnologico, porte/SLA/configurazione per ambiente, gestione errori
- **Architettura di Sistema** — vincoli architetturali, mappa microservizi, integrazioni, flussi end-to-end, decisioni architetturali (ADR), crosscutting concepts

Output in formato **Markdown** e **Word (.docx)** con template aziendale.

---

## Indice

1. [Requisiti](#1-requisiti)
2. [Installazione](#2-installazione)
3. [Come si usa](#3-come-si-usa)
4. [Cosa viene documentato](#4-cosa-viene-documentato)
5. [Linguaggi e build system supportati](#5-linguaggi-e-build-system-supportati)
6. [Classificazione file e priorità](#6-classificazione-file-e-priorità)
7. [Cosa succede quando lo lancio](#7-cosa-succede-quando-lo-lancio)
8. [Output generato](#8-output-generato)
9. [Provalo con il progetto di esempio](#9-provalo-con-il-progetto-di-esempio)
10. [Riferimento opzioni CLI](#10-riferimento-opzioni-cli)
11. [Domande frequenti](#11-domande-frequenti)
12. [Per sviluppatori](#12-per-sviluppatori)

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
pip3 install -e /percorso/ai-doc-generator
```

Verifica:
```bash
python3 -m docgen --help
```

---

## 3. Come si usa

DocGen ha **2 modalità principali** più utility di conversione e pulizia:

### 3.1 — Dry Run (anteprima gratuita)

Analizza il progetto senza chiamare API. Mostra statistiche, classificazione file, microservizi rilevati, sotto-moduli, endpoint, stima costi.

```bash
python3 -m docgen /percorso/progetto --dry-run -n "Nome Progetto"
```

**Costo**: zero. Utile come primo passo per verificare che DocGen riconosca correttamente il progetto.

### 3.2 — Agent Export ⭐ Consigliata

Genera un pacchetto di contesto strutturato che un agente AI (GitHub Copilot, Kiro, Claude Code) usa per generare la documentazione leggendo i file direttamente dal workspace. Nessuna API key necessaria.

```bash
python3 -m docgen /percorso/progetto --agent-export -n "Nome Progetto"
```

Produce nella cartella `<progetto>/DocGen/`:

**Progetto singolo:**
- `docgen_context.md` — contesto completo con struttura progetto, analisi statica, file classificati per urgenza, istruzioni operative e struttura documenti
- `docgen_files.json` — dati machine-readable
- `docgen_index.md` — indice

**Progetto multi-microservizio:**
- `docgen_instructions.md` — istruzioni generali e struttura documenti
- `docgen_context_<servizio>.md` — un file per ogni microservizio, con sotto-moduli Maven/Gradle mostrati come sezioni interne
- `docgen_files.json` + `docgen_index.md`

**Workflow completo:**
1. Lancia `--agent-export`
2. Apri il progetto in VS Code
3. Dai all'agente: *"Leggi `DocGen/docgen_context.md` e segui le istruzioni per generare la documentazione"*
4. L'agente legge i file sorgente e genera i documenti `.md`
5. Converti in Word: `python3 -m docgen --render DocGen/*.md --meta PROGETTO="Nome"`
6. Pulisci i temporanei: `python3 -m docgen --cleanup DocGen/`

### 3.3 — Conversione DOCX con template aziendale

Converte i file `.md` in `.docx` con formattazione aziendale: copertina, intestazione, piè di pagina, stili Word.

```bash
python3 -m docgen --render DocGen/*.md --meta PROGETTO="Nome Progetto" CLIENTE="Nome Cliente"
```

Metadati personalizzabili con `--meta`:

| Chiave | Default | Esempio |
|--------|---------|---------|
| `INTESTAZIONE_ENTE` | XXXX | `"MINISTERO DELLA DIFESA"` |
| `CLIENTE` | XXXX | `"Nome Cliente"` |
| `PROGETTO` | XXXX | `"Nome Progetto"` |
| `REDATTO_DA` | DocGen (generazione automatica) | `"Mario Rossi"` |
| `APPROVATO_DA` | XXXX | `"Mario Bianchi"` |
| `VERSIONE` | 1.0 | `"2.0"` |
| `STATO` | Bozza | `"Approvato"` |

Per usare un template diverso: `--template /percorso/template.docx`

### 3.4 — Pulizia file temporanei

```bash
python3 -m docgen --cleanup DocGen/
```

Rimuove i file di contesto dell'agent-export lasciando solo i documenti finali `.md` e `.docx`.

---

## 4. Cosa viene documentato

### Specifica Funzionale (IEEE 830)

| Sezione | Contenuto |
|---------|-----------|
| Introduzione | Scopo, ambito (incluso cosa il sistema NON fa), glossario |
| Descrizione generale | Panoramica, attori con ruoli, vincoli, limitazioni note |
| Requisiti funzionali | Formato [FUN-NNN] con attore, pre/post-condizioni, priorità |
| Casi d'uso | Diagramma Mermaid attori→UC, UC dettagliati con flussi alternativi ed eccezioni |
| Modello dati funzionale | Entità business + diagramma `erDiagram` |
| **Dati di dominio** ⭐ | Enum con valori e significato business, macchine a stati con transizioni, codici lookup (es. tipi ricorso, stati pratica) |
| Interfaccia utente | Schermate principali + diagramma navigazione |
| Integrazioni esterne | Sistemi terzi, API consumate |
| Regole di business | Formato [RB-NNN] con implementazione, vincolo violato, impatto |
| Requisiti non funzionali | Prestazioni/SLA, sicurezza, usabilità, disponibilità |
| Matrice funzionalità-componenti | Requisito → componente → modulo |
| Matrice CRUD | Entità × attore con operazioni C/R/U/D |

### Specifica Tecnica (IEEE 1016)

| Sezione | Contenuto |
|---------|-----------|
| Architettura | Pattern architetturale, diagramma generale, diagramma componenti |
| Stack tecnologico | Tabella tecnologia/versione/scopo da pom.xml/package.json/build.gradle |
| Dettaglio backend | Struttura package, tabella API REST completa, diagramma ER tecnico con tutti i campi, logica di business, sicurezza/autenticazione |
| Dettaglio frontend | Struttura moduli, tabella routing, componenti, servizi, gestione stato |
| **Configurazione per ambiente** ⭐ | Variabili d'ambiente, **porte di servizio** (dev/staging/prod), **URL servizi esterni**, **SLA e performance targets** |
| Integrazioni esterne | API consumate, database, servizi di autenticazione |
| Requisiti non funzionali tecnici | Prestazioni, logging, gestione errori, testing |
| Flussi operativi | Diagrammi `sequenceDiagram` per i flussi principali con flusso di errore |
| Flussi asincroni | Code, pub/sub, webhook con diagrammi sequenza |
| Catalogo errori | Tabella codice/messaggio/contesto/HTTP status |
| Debito tecnico | TODO/FIXME, config insicure, API deprecate |

### Architettura di Sistema (arc42)

| Sezione | Contenuto |
|---------|-----------|
| **Vincoli architetturali** ⭐ | Vincoli tecnologici (versioni JDK/framework), organizzativi, normativi (GDPR, PA), infrastrutturali |
| Mappa microservizi | Tabella servizi + diagramma architetturale con porte reali |
| Integrazioni | Matrice dipendenze, pattern comunicazione, autenticazione cross-service |
| Flussi end-to-end | 3-5 flussi principali con `sequenceDiagram` multi-servizio |
| Modello dati complessivo | DB per servizio, relazioni cross-service, ER di sistema |
| Stack unificato | Tecnologie condivise tra tutti i servizi |
| Deployment | Diagramma infrastruttura con porte reali, configurazione condivisa |
| **Decisioni architetturali** ⭐ | ADR (Architecture Decision Records): contesto/decisione/conseguenze/evidenza nel codice |
| **Crosscutting concepts** ⭐ | Autenticazione/JWT cross-service, logging centralizzato, error handling trasversale, gestione configurazione, sicurezza trasversale |
| Requisiti non funzionali trasversali | Scalabilità, resilienza, monitoring, testing cross-service |
| Matrice microservizio-funzionalità | Funzionalità → microservizio responsabile → microservizi coinvolti |

---

## 5. Linguaggi e build system supportati

### Linguaggi

| Linguaggio | Framework | Cosa rileva |
|---|---|---|
| **Java** | Spring Boot, Spring Security, JPA/Hibernate | Controller, Service, Entity, Repository, endpoint REST, campi JPA, listener eventi, aspect, security config |
| **C#** | ASP.NET Core, EF Core | Controller `[ApiController]`, DbContext, Entity `[Table]`/`[Key]`, dipendenze NuGet, `appsettings.json` |
| **TypeScript/JS** | Angular, NestJS, Express | Componenti, servizi, routing (eager + lazy), moduli, dipendenze NPM |
| **Python** | FastAPI, Flask, Django | Endpoint, modelli Django/SQLAlchemy, dipendenze |
| **Altro** | Go, Rust, Ruby, PHP | Estrazione dipendenze base |

### Build system — rilevamento microservizi

DocGen rileva automaticamente i microservizi e i loro sotto-moduli in base al build system:

| Build system | Rilevamento servizio | Rilevamento sotto-moduli |
|---|---|---|
| **Maven** | `pom.xml` nella prima directory | Sotto-dir con `pom.xml` propri |
| **Gradle** | `build.gradle` / `settings.gradle` | Sotto-dir con `build.gradle` propri |
| **Ant** | `build.xml` | Sotto-dir con `build.xml` propri |
| **.NET** | `.csproj` nella prima directory | — |
| **NPM/Node** | `package.json` | Monorepo Nx/Lerna (`apps/`, `packages/`) |
| **Nessun build file** | Nome della directory | — |

Un microservizio Maven multi-modulo (es. `administration-api/core`, `administration-api/web`) genera **un solo documento** con i sotto-moduli mostrati come sezioni interne — non documenti separati.

---

## 6. Classificazione file e priorità

DocGen classifica ogni file e lo assegna a una priorità di lettura per l'agente:

| Priorità | Categorie | Descrizione |
|----------|-----------|-------------|
| 🔴 **Obbligatori** | `controller`, `service`, `business_critical` | Logica principale, API, regole di business, listener eventi, aspect, security config |
| 🟡 **Importanti** | `entity`, `repository`, `config`, `dto`, `dbcontext`, `app_config`, `build_config`, `package_config` | Modello dati, configurazioni, dipendenze. I file `app_config` contengono porte, SLA, URL servizi |
| ⚪ **Supporto** | `test`, `util`, `style`, `template`, ecc. | Leggere solo se serve contesto aggiuntivo |

I file `business_critical` vengono rilevati automaticamente per nome (es. `*Listener`, `*Handler`, `*Validator`, `*Aspect`, `*Security`) e per contenuto (es. `@RabbitListener`, `@KafkaListener`, `@ControllerAdvice`, `SecurityFilterChain`).

---

## 7. Cosa succede quando lo lancio

4 fasi automatiche:

1. **Scansione** — Trova i file sorgente, ignora `node_modules`, `target`, `bin`, `obj`, `.git`, ecc. Classifica ogni file per categoria, priorità, microservizio e sotto-modulo.

2. **Analisi statica** — Estrae endpoint REST, entità DB, route frontend, componenti, dipendenze, configurazione database. Tutto senza eseguire il codice.

3. **Pianificazione** — Raggruppa i file in chunk per microservizio (rispettando il budget token). Rileva automaticamente microservizi e sotto-moduli.

4. **Export** — Con `--agent-export`, genera il pacchetto di contesto strutturato con istruzioni operative per l'agente e si ferma. Con API diretta, chiama Claude e produce i documenti.

---

## 8. Output generato

Output in `<progetto>/DocGen/`:

| File | Presente in |
|------|-------------|
| `struttura_progetto.txt` | Sempre |
| `analisi_statica.md` | Sempre |
| `docgen_context.md` | `--agent-export` progetto singolo |
| `docgen_instructions.md` | `--agent-export` multi-microservizio |
| `docgen_context_<servizio>.md` | `--agent-export` multi-microservizio (uno per servizio) |
| `docgen_files.json` | `--agent-export` |
| `docgen_index.md` | `--agent-export` |

Documenti generati dall'agente (salvati in `DocGen/`):

| Documento | Progetto singolo | Multi-microservizio |
|-----------|-----------------|---------------------|
| `specifica_funzionale.md` | ✅ | ✅ per servizio + `specifica_funzionale_completa.md` |
| `specifica_tecnica.md` | ✅ | ✅ per servizio + `specifica_tecnica_completa.md` |
| `architettura_sistema.md` | — | ✅ |

---

## 9. Provalo con il progetto di esempio

```bash
# Anteprima (gratuita)
python3 -m docgen ./test-project --dry-run -n "Gestione Utenti PA"

# Agent export (gratuito)
python3 -m docgen ./test-project --agent-export -n "Gestione Utenti PA"

# Poi dai all'agente:
# "Leggi DocGen/docgen_context.md e segui le istruzioni per generare la documentazione"

# Converti in Word
python3 -m docgen --render DocGen/*.md --meta PROGETTO="Gestione Utenti PA"

# Pulisci i temporanei
python3 -m docgen --cleanup DocGen/
```

---

## 10. Riferimento opzioni CLI

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
| `-m`, `--model` | `claude-sonnet-4-20250514` | Modello Claude (solo API diretta) |
| `--chunk-budget` | 80000 | Token per chunk |
| `--max-tokens` | 200000 | Limite contesto modello |

---

## 11. Domande frequenti

### Il dry-run e l'agent-export costano qualcosa?

**No.** Nessuna chiamata API. Completamente gratuiti e locali.

### Funziona con progetti Maven multi-modulo?

**Sì.** DocGen rileva automaticamente la struttura parent/modulo. Un microservizio con 5 sotto-moduli Maven genera **un solo documento** (non 5), con i sotto-moduli mostrati come sezioni interne. Questo vale anche per Gradle multi-modulo.

### Funziona con .NET + Angular?

**Sì.** Rileva controller ASP.NET Core, entità EF Core, dipendenze NuGet, `appsettings.json`. Per Angular: componenti, servizi, routing, moduli, dipendenze NPM.

### Cosa sono i "dati di dominio"?

Enum, costanti di stato, codici business presenti nel codice (es. `TipoRicorso.TAR`, `StatoPratica.APPROVATO`). DocGen istruisce l'agente a cercarli attivamente e documentarli con il loro significato business — informazione fondamentale per chi deve manutenere o evolvere il sistema.

### Cosa sono le "decisioni architetturali" nel documento di architettura?

Architecture Decision Records (ADR) deducibili dal codice: perché JWT invece di session, perché pattern Repository, perché code async invece di chiamate sincrone. DocGen istruisce l'agente a documentarle con contesto, decisione, conseguenze ed evidenza nel codice.

### I miei dati vengono inviati da qualche parte?

In modalità API diretta, il codice viene inviato all'API di Anthropic (Claude). In `--dry-run` e `--agent-export` **non viene inviato nulla**. Verifica le policy Anthropic per vincoli di riservatezza.

### Cosa succede se un file è troppo grande?

File oltre 500KB vengono saltati. File grandi vengono troncati con limiti adattivi per categoria: 80K caratteri per `business_critical`/`service`/`controller`, 40K per il resto.

---

## 12. Per sviluppatori

### Struttura del codice

```
docgen/
├── main.py               # CLI, orchestrazione, agent-export
├── config.py             # Configurazione centralizzata
├── scanner.py            # Scansione filesystem, classificazione file, rilevamento servizi/moduli
├── analyzer.py           # Estrazione statica (endpoint, entità, route, dipendenze)
├── chunker.py            # Raggruppamento file per servizio con budget token + language_hint
├── generator.py          # Chiamate Claude API con retry
├── prompts.py            # Template prompt (IEEE 830 / IEEE 1016 / arc42)
├── renderer.py           # Conversione Markdown → DOCX (stile interno)
└── template_renderer.py  # Conversione Markdown → DOCX con template aziendale

templates/
├── template_aziendale.docx  # Template Word con placeholder
└── build_template.py        # Script per ricostruire il template

.github/skills/
└── docgen-documentation/    # Skill per avvio automatico tramite agente AI

tests/
└── test_docgen.py           # 198 test automatici

test-project/                # Progetto di esempio Spring Boot + Angular
```

### Architettura interna

**Rilevamento microservizi e sotto-moduli**: `scanner._detect_service_and_module()` distingue il *service* (microservizio, primo livello) dal *module* (sotto-modulo interno). La modalità hybrid si basa sul numero di *service*, non di *module* — un microservizio Maven multi-modulo conta come 1.

**Classificazione priorità**: ogni file riceve una priorità (🔴/🟡/⚪) basata sulla categoria. I file `app_config` (application.yml, appsettings.json) sono 🟡 perché contengono porte, SLA e URL operativi fondamentali per la documentazione.

**Language hint**: `chunker.Chunk.language_hint()` rileva linguaggi e framework nel chunk e li passa al prompt `ANALYZE_CHUNK` per orientare l'LLM sul contesto tecnologico.

**Prompt sicuri**: `prompts._format_prompt()` sostituisce solo i placeholder espliciti, lasciando intatti i blocchi Mermaid con `{` e `}` — evita `KeyError` nei template `erDiagram`/`sequenceDiagram`.

### Test

```bash
python3 -m pytest tests/ -v
```

---

## Licenza

Uso interno — Almaviva SpA
