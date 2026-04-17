# DocGen — Generatore Automatico di Documentazione da Codebase

**DocGen** analizza il codice sorgente di un progetto software e genera automaticamente 
due documenti professionali in italiano:

- **Specifica Funzionale** — requisiti, casi d'uso, flussi operativi, modello dati
- **Specifica Tecnica** — architettura, API REST, schema DB, diagrammi, stack tecnologico

I documenti vengono prodotti in formato **Markdown** e **Word (.docx)**, con copertina, 
formattazione professionale, tabelle e numerazione pagine.

---

## Indice

1. [Requisiti](#1-requisiti)
2. [Installazione](#2-installazione)
3. [Configurazione API Key](#3-configurazione-api-key)
4. [Come si usa](#4-come-si-usa)
5. [Cosa succede quando lo lancio](#5-cosa-succede-quando-lo-lancio)
6. [Cosa ottengo in output](#6-cosa-ottengo-in-output)
7. [Provalo subito con il progetto di esempio](#7-provalo-subito-con-il-progetto-di-esempio)
8. [Riferimento opzioni](#8-riferimento-opzioni)
9. [Domande frequenti](#9-domande-frequenti)
10. [Stima costi API](#10-stima-costi-api)
11. [Per sviluppatori](#11-per-sviluppatori)
12. [Roadmap Enterprise](#12-roadmap-enterprise)

---

## 1. Requisiti

Per usare DocGen servono solo due cose:

| Cosa | Dettaglio |
|------|-----------|
| **Python** | Versione 3.9 o superiore. Controlla con `python3 --version` nel terminale |
| **API Key Anthropic** | Serve per la generazione dei documenti (non serve per il dry-run). Si ottiene su [console.anthropic.com](https://console.anthropic.com/) |

Non serve installare Java, Node.js o altri runtime: DocGen legge il codice ma non lo esegue.

---

## 2. Installazione

Apri il terminale, entra nella cartella del progetto e installa le dipendenze:

```bash
cd ai-doc-generator
pip3 install -r requirements.txt
```

Se il comando `pip3` non funziona, prova con `pip install -r requirements.txt`.

Fatto. Non serve altro.

---

## 3. Configurazione API Key

La API key serve **solo per la generazione dei documenti** (non per il dry-run). 
Puoi ottenerla registrandoti su [console.anthropic.com](https://console.anthropic.com/).

**Su macOS/Linux**, apri il terminale e digita:
```bash
export ANTHROPIC_API_KEY=sk-ant-la-tua-chiave-qui
```

**Su Windows** (PowerShell):
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-la-tua-chiave-qui"
```

> **Nota**: questa impostazione dura solo per la sessione corrente del terminale. 
> Per renderla permanente, aggiungila al file `~/.zshrc` (macOS) o `~/.bashrc` (Linux).

---

## 4. Come si usa

DocGen si lancia dal terminale. Il comando base è:

```bash
python3 -m docgen <percorso-al-progetto-da-analizzare>
```

### 4.1 — Anteprima (dry-run)

Prima di spendere crediti API, fai un **dry-run** per vedere cosa DocGen ha trovato 
nel codice. Non chiama nessuna API esterna e non costa nulla:

```bash
python3 -m docgen ./percorso-al-mio-progetto --dry-run
```

Vedrai a schermo:
- Quanti file sono stati trovati e di che tipo
- Quali endpoint REST, entità, route e componenti sono stati rilevati
- Come verrà suddiviso il lavoro (chunk) e quanto costerà la generazione

### 4.2 — Generazione completa

Quando sei soddisfatto dell'anteprima, lancia senza `--dry-run`:

```bash
python3 -m docgen ./percorso-al-mio-progetto -n "Nome del Progetto"
```

L'opzione `-n` imposta il nome che apparirà nella copertina dei documenti. 
Se la ometti, verrà usato il nome della cartella.

### 4.3 — Scegliere dove salvare l'output

Di default i documenti vengono salvati in `./docgen_output/`. Per cambiare:

```bash
python3 -m docgen ./mio-progetto -n "Nome Progetto" -o ./cartella-output
```

### 4.4 — Scegliere il formato

```bash
# Solo Markdown (più veloce, niente Word)
python3 -m docgen ./mio-progetto -f md

# Solo Word
python3 -m docgen ./mio-progetto -f docx

# Entrambi (default)
python3 -m docgen ./mio-progetto -f all
```

---

## 5. Cosa succede quando lo lancio

DocGen lavora in **4 fasi automatiche**. Tutto viene mostrato a schermo con 
un log chiaro e una barra di avanzamento.

### Fase 1 — Scansione (pochi secondi)

Esplora tutte le cartelle del progetto e trova i file sorgente rilevanti 
(`.java`, `.ts`, `.html`, `.xml`, `.yml`, `.json`, ecc.). 
Ignora automaticamente cartelle inutili come `node_modules`, `.git`, `target`, `build`.

Ogni file viene classificato per tipo: controller, service, entity, component, configurazione, ecc.

**Non serve configurare nulla: funziona out-of-the-box.**

### Fase 2 — Analisi statica (pochi secondi)

Legge il contenuto dei file e ne estrae le informazioni strutturali senza eseguirli:
- Endpoint REST (es. `GET /api/utenti/{id}`)
- Entità del database con i loro campi
- Route del frontend Angular
- Componenti Angular con i loro selettori
- Dipendenze Maven e NPM
- Configurazione database (URL, driver, porta)

### Fase 3 — Generazione con AI (1-5 minuti)

> **Questa fase viene saltata in dry-run.**

Invia il codice a Claude (l'AI di Anthropic) in blocchi organizzati per modulo. 
L'AI analizza ogni blocco e poi produce i due documenti completi. 

Sono 3 sotto-fasi:
1. **Analisi moduli** — Un'analisi per ogni blocco di codice
2. **Documento Funzionale** — Sintesi orientata ai requisiti e ai flussi utente
3. **Documento Tecnico** — Sintesi orientata all'architettura e alle API

A schermo vedi una barra di avanzamento e, alla fine, il totale dei token usati 
e il costo stimato.

#### Progetto multi-microservizio (modalità ibrida)

Se DocGen rileva un progetto grande con **3 o più microservizi**, propone 
automaticamente una scelta interattiva:

```
Progetto multi-microservizio rilevato!

Sono stati rilevati 8 microservizi con 21 chunk totali.
Puoi scegliere come generare la documentazione:

[1] Per microservizio + Architettura di sistema (consigliato)
    → 16 documenti (funzionale + tecnica per servizio)
    → 1 documento architettura di sistema
    → Costo stimato: $X.XX

[2] Tutto insieme (modalità classica)
    → 2 documenti (funzionale + tecnica unici)
    → Costo stimato: $X.XX

[3] Annulla

Scelta (1/2/3):
```

**Opzione 1 (consigliata per progetti grandi):** genera una coppia di documenti 
(funzionale + tecnica) per ogni microservizio, più un **Documento di Architettura 
di Sistema** che descrive integrazioni, flussi cross-service e diagrammi di 
comunicazione. I file vengono organizzati in sottocartelle per microservizio.

**Opzione 2:** funziona come prima, generando 2 documenti unici per l'intero progetto.

### Fase 4 — Rendering (pochi secondi)

Converte i documenti Markdown in Word (.docx) con formattazione professionale:
copertina, titoli colorati, tabelle, code block e numerazione pagine.

---

## 6. Cosa ottengo in output

Nella cartella di output (default: `docgen_output/`) trovi:

### Sempre generati (anche in dry-run):

| File | Contenuto |
|------|-----------|
| `struttura_progetto.txt` | Lista di tutti i file trovati, organizzati per modulo, con categoria e priorità |
| `analisi_statica.md` | Riepilogo degli endpoint, entità, route, componenti e configurazioni rilevate |

### Generati con la chiamata AI (no dry-run):

| File | Contenuto |
|------|-----------|
| `DOC_FUNZIONALE_20260416_1430.md` | Specifica funzionale in Markdown |
| `DOC_FUNZIONALE_20260416_1430.docx` | Specifica funzionale in Word |
| `DOC_TECNICA_20260416_1430.md` | Specifica tecnica in Markdown |
| `DOC_TECNICA_20260416_1430.docx` | Specifica tecnica in Word |

> I nomi contengono data e ora (YYYYMMDD_HHMM), così puoi generare più versioni 
> senza sovrascrivere.

### Generati in modalità ibrida (multi-microservizio):

Se scegli l'opzione 1, la struttura output sarà:

```
docgen_output/
├── struttura_progetto.txt
├── analisi_statica.md
├── DOC_ARCHITETTURA_SISTEMA_20260416_1430.md
├── DOC_ARCHITETTURA_SISTEMA_20260416_1430.docx
├── contenzioso-api/
│   ├── DOC_FUNZIONALE_contenzioso-api_20260416_1430.md
│   ├── DOC_FUNZIONALE_contenzioso-api_20260416_1430.docx
│   ├── DOC_TECNICA_contenzioso-api_20260416_1430.md
│   └── DOC_TECNICA_contenzioso-api_20260416_1430.docx
├── security-manager-api/
│   └── ...
└── ...
```

Il **Documento di Architettura di Sistema** descrive:
- Mappa dei microservizi e le loro responsabilità
- Integrazioni e comunicazioni tra servizi (REST, messaggi, ecc.)
- Flussi operativi end-to-end con diagrammi di sequenza
- Modello dati complessivo e relazioni cross-service
- Stack tecnologico unificato
- Requisiti non funzionali trasversali

### Cosa contengono i documenti Word

- **Copertina** con titolo documento, nome progetto e data
- **Heading** formattati su 4 livelli (blu scuro)
- **Tabelle** con header colorato (es. lista API, requisiti)
- **Code block** con font monospace
- **Numerazione pagine** nel footer

---

## 7. Provalo subito con il progetto di esempio

Il repository include una cartella `test-project/` con un mini-progetto 
Spring Boot + Angular di esempio (gestione utenti PA).

### Passo 1 — Anteprima

```bash
python3 -m docgen ./test-project --dry-run -n "Gestione Utenti PA"
```

Dovresti vedere: 11 file trovati, 7 endpoint REST, 1 entità JPA (Utente), 
3 route Angular, 1 componente, 2 chunk pianificati, costo stimato ~$0.37.

### Passo 2 — Generazione (richiede API key)

```bash
export ANTHROPIC_API_KEY=sk-ant-la-tua-chiave-qui
python3 -m docgen ./test-project -n "Gestione Utenti PA" -o ./output-test
```

Nella cartella `output-test/` troverai i 4 documenti + i 2 file di analisi.

---

## 8. Riferimento opzioni

| Opzione | Esempio | Descrizione |
|---------|---------|-------------|
| `percorso` | `./mio-progetto` | **(obbligatorio)** Cartella del progetto da analizzare |
| `-n`, `--name` | `-n "Portale PA"` | Nome progetto (appare in copertina). Default: nome cartella |
| `-o`, `--output` | `-o ./docs` | Cartella dove salvare i documenti. Default: `./docgen_output` |
| `-f`, `--format` | `-f md` | Formato output: `all` (default), `md`, `docx` |
| `-d`, `--dry-run` | `--dry-run` | Solo anteprima. Non chiama API, non costa nulla |
| `-m`, `--model` | `-m claude-sonnet-4-20250514` | Modello Claude da usare. Normalmente non serve cambiarlo |
| `--chunk-budget` | `--chunk-budget 50000` | Token per blocco di codice. Default: 80000. Abbassalo se hai progetti molto grandi |
| `--max-tokens` | `--max-tokens 150000` | Limite contesto modello. Default: 200000 |

### Esempi completi

```bash
# Anteprima veloce
python3 -m docgen ./mio-progetto -d

# Generazione standard
python3 -m docgen ./mio-progetto -n "Sistema Protocollo" 

# Solo Markdown, output personalizzato
python3 -m docgen ./mio-progetto -n "Portale Servizi" -f md -o ./documenti

# Progetto grande, budget chunk ridotto
python3 -m docgen ./mio-progetto -n "ERP Ministero" --chunk-budget 50000
```

---

## 9. Domande frequenti

### Quali linguaggi/framework supporta?

| Stack | Cosa riconosce |
|-------|----------------|
| **Java / Spring Boot** | Controller, Service, Entity, Repository, endpoint REST, campi JPA, `pom.xml` |
| **Angular** | Componenti, servizi, routing (eager + lazy), moduli, `package.json` |
| **Configurazione** | `application.yml`, `.properties`, `Dockerfile`, `docker-compose.yml` |

Anche se il tuo progetto usa un framework diverso, DocGen analizzerà comunque 
i file sorgente — solo l'estrazione strutturata (endpoint, entità) sarà meno ricca.

### Quanto costa una generazione?

Dipende dalla dimensione del progetto. Usa `--dry-run` per vedere la stima prima di lanciare:

| Dimensione progetto | Costo stimato |
|---------------------|---------------|
| Piccolo (~10 file) | < $0.10 |
| Medio (~100 file) | $0.20 – $0.50 |
| Grande (~500 file) | $0.50 – $2.00 |
| Enterprise (~2000 file) | $2.00 – $5.00 |

### Il dry-run costa qualcosa?

**No.** Il dry-run non chiama nessuna API esterna. È completamente gratuito e locale.

### Posso usarlo su un progetto .NET / Python / React?

Sì, ma l'estrazione strutturata (endpoint, entità) è ottimizzata per Java Spring + Angular. 
Per altri stack, l'AI riceverà comunque il codice sorgente e produrrà documentazione 
basandosi su quello che trova, ma le tabelle di analisi statica saranno meno dettagliate.

### I miei dati/codice vengono inviati da qualche parte?

Il codice sorgente viene inviato all'API di Anthropic (Claude) per la generazione dei documenti. 
In dry-run non viene inviato nulla. Verifica le policy di Anthropic se hai vincoli di riservatezza.

### Funziona su Windows?

Sì. Usa `python` al posto di `python3` e imposta la variabile d'ambiente con PowerShell 
(`$env:ANTHROPIC_API_KEY = "..."`).

### Cosa succede se un file è troppo grande?

I file oltre 500KB vengono saltati automaticamente (sono probabilmente generati). 
I file oltre 15.000 caratteri vengono troncati intelligentemente (inizio + fine) 
per rientrare nel budget.

### Cosa succede se l'API dà errore?

DocGen ritenta automaticamente fino a 3 volte con attesa progressiva. Se un blocco 
fallisce, la generazione prosegue con gli altri — otterrai documenti parziali 
piuttosto che nessun documento.

---

## 10. Stima costi API

DocGen usa il modello Claude Sonnet di Anthropic. I costi attuali sono:

| | Prezzo |
|---|--------|
| Token input (il codice che invii) | $3 per milione di token |
| Token output (i documenti generati) | $15 per milione di token |

La stima viene mostrata sia nel dry-run che durante la generazione, 
così hai sempre il controllo.

---

## 11. Per sviluppatori

### Struttura del codice

```
docgen/
├── main.py          # CLI e orchestrazione delle 4 fasi
├── config.py        # Configurazione centralizzata
├── scanner.py       # Scansione filesystem e classificazione file
├── analyzer.py      # Estrazione statica (endpoint, entità, route...)
├── chunker.py       # Raggruppamento file per modulo con budget token
├── generator.py     # Chiamate Claude API con retry
├── prompts.py       # Template prompt in italiano
└── renderer.py      # Conversione Markdown → DOCX

tests/
└── test_docgen.py   # 98 test automatici

test-project/        # Progetto di esempio per provare DocGen
```

### Pipeline

```
Codebase → Scanner → Analyzer → Chunker → Generator (Claude) → Renderer → MD + DOCX
```

### Test

```bash
pip3 install pytest
python3 -m pytest tests/ -v
```

---

## 12. Roadmap Enterprise

Funzionalità pianificate per il futuro (non ancora implementate):

- **MCP Server** — Integrazione in Claude Code / Cursor per generazione on-demand durante lo sviluppo
- **Azure DevOps Extension** — Tab dedicata per generazione automatica a ogni release
- **Pipeline CI/CD** — Trigger automatico in Jenkins / GitLab CI / GitHub Actions
- **Template PA Custom** — Template DOCX conformi a linee guida AgID e Ministeri specifici
- **Supporto .NET e Python backend** — ASP.NET Core, FastAPI, Django
- **Diagrammi avanzati** — PlantUML, Draw.io oltre a Mermaid
- **RAG con documentazione esistente** — Integrazione Confluence/SharePoint come contesto aggiuntivo

---

## Licenza

Uso interno — Almaviva SpA
