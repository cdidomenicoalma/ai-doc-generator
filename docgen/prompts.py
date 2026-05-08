"""Template prompt in italiano per le chiamate Claude API e per l'agent-export."""

import re as _re


def _format_prompt(template: str, **kwargs: str) -> str:
    """Sostituisce i placeholder {key} nel template senza interpretare i blocchi Mermaid.

    A differenza di str.format(), questa funzione sostituisce SOLO i placeholder
    esplicitamente passati come kwargs, lasciando intatti tutti gli altri {}.
    Questo evita KeyError sui blocchi erDiagram/sequenceDiagram di Mermaid.
    """
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result

SYSTEM_PROMPT = """Sei un analista software senior specializzato in progetti IT istituzionali e aziendali.

Il tuo compito è produrre documentazione tecnica e funzionale professionale, destinata a team tecnici interni che la useranno come riferimento per manutenzione, evoluzione e collaudo del sistema.

Regole fondamentali:
- L'output deve essere SEMPRE in Markdown strutturato e in lingua italiana.
- Non inventare funzionalità, endpoint, entità o comportamenti non presenti nel codice sorgente.
- Usa terminologia tecnica italiana (es. "endpoint", "entità", "componente", "servizio", "flusso").
- Se una sezione non ha dati sufficienti nel codice analizzato, scrivi esplicitamente:
  `> ⚠️ Da completare — informazioni non rilevabili dal codice sorgente in questa fase.`
  NON inventare contenuto per riempire la sezione. Tornerai su queste sezioni nella fase di revisione finale.
- Sii preciso e professionale. Il documento sarà usato in contesti istituzionali e di collaudo.
- Non aggiungere disclaimer o note sulla natura AI del documento.
- I diagrammi Mermaid devono essere sintatticamente corretti e renderizzabili. Usa sempre la sintassi standard.
"""


ANALYZE_CHUNK = """Analizza il seguente modulo di codice sorgente ed estrai le informazioni strutturate richieste.

## Contesto progetto
Nome progetto: {project_name}
Linguaggi/framework rilevati in questo modulo: {language_hint}

{static_analysis}

## Codice sorgente del modulo
{chunk_content}

## Istruzioni
Analizza il codice sopra e produci un report strutturato. Includi SOLO le sezioni per cui hai dati concreti nel codice — ometti completamente le sezioni senza informazioni rilevabili (non scrivere "Da completare" nelle analisi di chunk, lo farai solo nei documenti finali).

### 1. Scopo del modulo
Descrivi brevemente lo scopo e la responsabilità di questo modulo nel contesto del progetto.

### 2. Funzionalità principali
Lista le funzionalità implementate (operazioni CRUD, logiche di business, ecc.).

### 3. Componenti chiave
Per ogni file significativo: nome file, tipo (Controller/Service/Entity/Component/ecc.), responsabilità principale.

### 4. Flussi operativi principali
Descrivi i flussi principali con la sequenza di chiamate, ad esempio:
`GET /api/utenti → UtenteController.getAll() → UtenteService.findAll() → UtenteRepository → List<Utente>`
Includi anche i flussi di errore (validazione fallita, not found, ecc.).

### 5. Modello dati
Se sono presenti entità/modelli, descrivi: nome entità, campi con tipo e vincoli, relazioni con altre entità (anche se in altri moduli), chiavi primarie/esterne.

### 6. Dati di dominio
**Sezione critica**: documenta TUTTI i valori di dominio trovati in questo modulo:
- **Enum e costanti**: per ogni enum/costante, elenca ogni valore con il suo significato business (es. `TipoRicorso.TAR = "Tribunale Amministrativo Regionale"`)
- **Macchine a stati**: se ci sono stati, documenta le transizioni ammesse
- **Codici e lookup**: codici business con descrizione (es. codici tipo, codici ente, codici stato)
- **Configurazione operativa** (solo se presente app_config): porte di servizio, URL di sistemi esterni, timeout, SLA

### 6. Interfaccia utente (solo se presente frontend)
Descrivi le viste, i componenti, le interazioni utente e il routing.

### 7. Regole di business e vincoli
Identifica e documenta OGNI regola di business implementata nel codice:
- Vincoli di validazione (cosa viene rifiutato e perché, con il messaggio di errore se presente)
- Vincoli di relazione tra entità (incompatibilità, obbligatorietà condizionale)
- Comportamenti condizionali basati su stato, configurazione o ambiente
- Logica di cascata (cosa succede quando si elimina/modifica un'entità)
- Idempotenza e gestione duplicati
Per ogni regola indica: classe/metodo dove è implementata, cosa succede se il vincolo è violato (eccezione, codice errore, HTTP status).

### 8. Flussi asincroni e integrazioni event-driven
(Includi solo se il modulo produce o consuma messaggi/eventi: queue, pub/sub, webhook, signal, event bus)
Per ciascuno: direzione (in/out), canale/topic, payload, trigger, effetto alla ricezione.

### 9. Gestione errori e messaggi
Elenca i codici/messaggi di errore definiti nel codice:
- Costante o codice identificativo
- Messaggio utente
- Contesto di utilizzo (quando viene lanciato)
- HTTP status associato (se applicabile)

### 10. Criticità e osservazioni tecniche
Segnala esplicitamente (solo se rilevato nel codice):
- Configurazioni potenzialmente insicure (CORS aperti, auth disabilitabile, credenziali hardcoded, endpoint non protetti)
- Bug potenziali (race condition, null pointer, risorse non chiuse, injection)
- Debito tecnico (codice commentato, TODO/FIXME, pattern non standard)
- Differenze di comportamento tra ambienti (dev/staging/prod)
"""


FUNCTIONAL_DOC = """Genera il Documento di Specifica Funzionale completo per il progetto "{project_name}".

## Analisi statica del progetto
{static_analysis}

## Analisi dettagliate dei moduli
{module_analyses}

## Istruzioni
Produci un documento Markdown professionale seguendo ESATTAMENTE questa struttura.

Per le sezioni senza dati sufficienti scrivi:
`> ⚠️ Da completare — informazioni non rilevabili dal codice sorgente in questa fase.`
NON inventare contenuto. Queste sezioni verranno completate nella fase di revisione finale.

---

# Specifica Funzionale — {project_name}

## 1. Introduzione
### 1.1 Scopo del documento
### 1.2 Ambito del sistema
Descrivi cosa fa il sistema, per chi, e cosa NON fa (limiti espliciti del sistema).
### 1.3 Riferimenti
### 1.4 Glossario

## 2. Descrizione generale del sistema
### 2.1 Panoramica
### 2.2 Utenti e attori del sistema
Per ogni attore: nome, ruolo, operazioni che può compiere.
### 2.3 Vincoli e assunzioni
### 2.4 Limitazioni note
Descrivi esplicitamente le funzionalità che il sistema NON implementa o che sono fuori scope, deducibili dal codice (es. funzionalità commentate, TODO, endpoint stub).

## 3. Requisiti funzionali
Per ogni requisito usa il formato:

**[FUN-001] Nome requisito**
- Descrizione: ...
- Attore: ...
- Pre-condizioni: ...
- Flusso principale: ...
- Post-condizioni: ...
- Priorità: Alta/Media/Bassa

Numera progressivamente: FUN-001, FUN-002, ecc.

## 4. Casi d'uso dettagliati

### Diagramma casi d'uso
Includi un diagramma Mermaid che mostra gli attori e i casi d'uso principali:

```mermaid
flowchart LR
    Actor1([Attore 1]) --> UC1[Caso d'uso 1]
    Actor1 --> UC2[Caso d'uso 2]
    Actor2([Attore 2]) --> UC3[Caso d'uso 3]
```

### Casi d'uso dettagliati
Per ogni caso d'uso PRINCIPALE (che modifica lo stato del sistema):

#### UC-001: [Titolo]
- **Attore**: chi inizia l'azione
- **Precondizioni**: stato del sistema prima
- **Flusso principale**: sequenza numerata di passi
- **Flussi alternativi**: almeno 1 per caso d'uso (validazione fallita, dato non trovato, permessi insufficienti, conflitto, timeout)
- **Eccezioni**: condizioni di errore, codice errore, messaggio, HTTP status
- **Postcondizioni**: stato del sistema dopo l'operazione

Non produrre casi d'uso triviali (es. "l'utente apre la pagina"). Concentrati su operazioni che modificano lo stato.

## 5. Modello dati funzionale
Descrivi le entità dal punto di vista funzionale (non tecnico), le relazioni tra esse.

### Diagramma ER funzionale
```mermaid
erDiagram
    ENTITA_A {
        tipo campo1
        tipo campo2
    }
    ENTITA_B {
        tipo campo1
    }
    ENTITA_A ||--o{ ENTITA_B : "relazione"
```

## 6. Dati di dominio
Documenta TUTTI i valori di dominio trovati nel codice. Questa sezione è fondamentale per la comprensione del sistema.

### 6.1 Enumerazioni e tipi
Per ogni enum/costante di dominio trovata nel codice:

| Tipo | Valore | Descrizione business |
|------|--------|---------------------|
| NomeTipo | VALORE_1 | Descrizione del valore |

### 6.2 Macchine a stati
Per ogni entità con stati, documenta le transizioni ammesse:

| Stato iniziale | Evento/Azione | Stato finale | Condizioni |
|----------------|---------------|--------------|------------|
| BOZZA | invio | INVIATO | utente autenticato |

### 6.3 Codici e lookup
Elenca tutti i codici di dominio con il loro significato (es. codici tipo ricorso, codici ente, codici stato).

## 7. Interfaccia utente
Descrivi le schermate principali e i flussi di navigazione.

### Diagramma di navigazione
```mermaid
flowchart TD
    Login --> Dashboard
    Dashboard --> SchermataA
    Dashboard --> SchermataB
```

## 7. Interfaccia utente
Descrivi le schermate principali e i flussi di navigazione.

### Diagramma di navigazione
```mermaid
flowchart TD
    Login --> Dashboard
    Dashboard --> SchermataA
    Dashboard --> SchermataB
```

## 8. Integrazioni e interfacce esterne
Descrivi le integrazioni con sistemi esterni, API consumate, sistemi di autenticazione.

## 9. Regole di business
Catalogo delle regole di business estratte dal codice:

### RB-001: [Nome regola]
- **Descrizione**: cosa impone la regola
- **Implementazione**: classe e metodo dove è implementata
- **Vincolo**: cosa succede se la regola è violata (eccezione, errore, blocco, HTTP status)
- **Impatto**: quali casi d'uso sono influenzati

Includi: validazioni, vincoli di relazione, comportamenti condizionali, logiche di cascata, idempotenza.

## 10. Requisiti non funzionali
### 10.1 Prestazioni e SLA
Documenta i target di performance trovati nel codice o nella configurazione (timeout, rate limit, connection pool, response time atteso).
### 10.2 Sicurezza
### 10.3 Usabilità
### 10.4 Disponibilità e affidabilità

## 11. Matrice funzionalità-componenti
Tabella che mappa ogni requisito funzionale ai componenti che lo implementano:

| Requisito | Componente/Classe | Modulo | Note |
|-----------|-------------------|--------|------|
| FUN-001   | NomeClasse        | backend | ... |

## 12. Matrice CRUD
Tabella che mostra quali attori/componenti eseguono operazioni Create/Read/Update/Delete su ogni entità:

| Entità | Create | Read | Update | Delete | Note |
|--------|--------|------|--------|--------|------|
| NomeEntità | Attore/Componente | Attore/Componente | Attore/Componente | Attore/Componente | ... |

---

## FASE DI REVISIONE FINALE

Dopo aver completato tutte le sezioni, esegui obbligatoriamente questa revisione:

1. **Revisione sezioni incomplete**: cerca tutte le sezioni marcate con `⚠️ Da completare`. Per ciascuna, verifica se hai trovato informazioni rilevanti leggendo i file del progetto. Se sì, completa la sezione. Se no, lascia il marker.

2. **Completezza sezione Dati di dominio (6)**: verifica di aver documentato TUTTI gli enum, le costanti di stato e i codici di dominio trovati nel codice. Cerca file con `Enum`, `Constant`, `Status`, `Type`, `Code` nel nome.

3. **Coerenza interna**: verifica che:
   - Gli attori descritti nella sezione 2.2 corrispondano a quelli usati nei casi d'uso (sezione 4)
   - I requisiti funzionali (sezione 3) abbiano tutti un caso d'uso corrispondente (sezione 4)
   - Le entità nel modello dati (sezione 5) corrispondano alle regole di business (sezione 9)
   - La matrice CRUD (sezione 12) sia coerente con i casi d'uso (sezione 4)
   - I dati di dominio (sezione 6) siano referenziati nelle regole di business (sezione 9)

4. **Completezza diagrammi**: verifica che tutti i diagrammi Mermaid siano sintatticamente corretti.

Se trovi incoerenze, correggile direttamente nel documento prima di consegnare.
"""


TECHNICAL_DOC = """Genera il Documento di Specifica Tecnica completo per il progetto "{project_name}".

## Analisi statica del progetto
{static_analysis}

## Analisi dettagliate dei moduli
{module_analyses}

## Istruzioni
Produci un documento Markdown professionale seguendo ESATTAMENTE questa struttura.

Per le sezioni senza dati sufficienti scrivi:
`> ⚠️ Da completare — informazioni non rilevabili dal codice sorgente in questa fase.`
NON inventare contenuto. Queste sezioni verranno completate nella fase di revisione finale.

---

# Specifica Tecnica — {project_name}

## 1. Introduzione
### 1.1 Scopo del documento
### 1.2 Ambito del sistema
### 1.3 Riferimenti
### 1.4 Glossario tecnico

## 2. Architettura del sistema
### 2.1 Architettura generale
Descrivi il pattern architetturale (layered, hexagonal, MVC, ecc.).

### Diagramma architetturale
```mermaid
flowchart TD
    Client[Client / Browser] --> Frontend[Frontend Layer]
    Frontend --> API[API Layer / Controller]
    API --> Service[Service Layer]
    Service --> Repository[Repository / DAO Layer]
    Repository --> DB[(Database)]
```
Adatta il diagramma alla struttura reale del progetto.

### 2.2 Pattern architetturali
Elenca i pattern rilevati nel codice (Repository Pattern, Service Layer, DTO, ecc.) con una breve descrizione di come sono implementati.

### 2.3 Diagramma dei componenti
```mermaid
flowchart LR
    subgraph Backend
        Controller --> Service
        Service --> Repository
        Service --> ExternalClient
    end
    subgraph Frontend
        Component --> ServiceFE[Angular Service]
        ServiceFE --> Controller
    end
```
Adatta con i componenti reali rilevati.

## 3. Stack tecnologico
| Tecnologia | Versione | Scopo |
|---|---|---|
Popola con tutte le tecnologie rilevate dall'analisi statica (dipendenze Maven/NPM/NuGet).

## 4. Dettaglio backend
### 4.1 Struttura dei package
Descrivi l'organizzazione dei package/namespace con le responsabilità di ciascuno.

### 4.2 API REST
Tabella completa degli endpoint rilevati:
| Metodo | Endpoint | Descrizione | Controller | Autenticazione richiesta |
|---|---|---|---|---|
Popola con i dati dell'analisi statica.

### 4.3 Modello dati tecnico
Descrivi le entità con tutti i campi, tipi, vincoli e annotazioni.

#### Diagramma ER tecnico
```mermaid
erDiagram
    TABELLA_A {
        Long id PK
        String campo1
        String campo2 FK
    }
    TABELLA_B {
        Long id PK
        String campo1
    }
    TABELLA_A ||--o{ TABELLA_B : "foreign key"
```
Includi tutti i campi rilevati dall'analisi statica con tipi e vincoli (@Id, @NotNull, ecc.).

### 4.4 Logica di business
Descrivi le classi di servizio principali, le loro responsabilità e le dipendenze tra di esse.

### 4.5 Sicurezza e autenticazione
Descrivi il meccanismo di autenticazione/autorizzazione implementato (JWT, session, OAuth2, Spring Security, ecc.), i ruoli definiti e le regole di accesso agli endpoint.

## 5. Dettaglio frontend (solo se presente)
### 5.1 Struttura dei moduli
### 5.2 Routing
Tabella delle route con componente associato e lazy loading:
| Path | Componente | Lazy | Guard |
|---|---|---|---|

### 5.3 Componenti principali
Per ogni componente significativo: nome, selector, responsabilità, input/output principali.

### 5.4 Servizi e comunicazione con il backend
Descrivi i servizi Angular/frontend, gli endpoint che chiamano e il formato dei dati scambiati.

### 5.5 Gestione dello stato
Descrivi come viene gestito lo stato dell'applicazione (servizi con BehaviorSubject, NgRx, Vuex, Redux, ecc.).

## 6. Configurazione e deployment
### 6.1 Configurazione applicativa
Descrivi i file di configurazione rilevati (application.yml, appsettings.json, ecc.) e i parametri principali.

### 6.2 Variabili d'ambiente e configurazione per ambiente
| Variabile | Tipo | Default | Obbligatoria | Descrizione |
|-----------|------|---------|--------------|-------------|
Elenca tutte le variabili d'ambiente rilevate nei file di configurazione.

### 6.3 Porte e URL di servizio
Documenta le porte e gli URL per ogni ambiente rilevato (dev/staging/prod):
| Servizio/Componente | Porta dev | Porta prod | URL/Host |
|---------------------|-----------|------------|----------|
Ricava questi dati dai file application.yml, application-dev.yml, application-prod.yml, appsettings.json.

### 6.4 SLA e performance targets
Documenta i target di performance trovati nella configurazione o nei commenti:
| Parametro | Valore | Contesto |
|-----------|--------|----------|
Cerca: timeout di connessione, connection pool size, rate limit, max request size, session timeout.

### 6.5 Requisiti di sistema
### 6.6 Istruzioni di build e deploy

## 7. Integrazioni esterne
### 7.1 API consumate
### 7.2 Database
Descrivi il database rilevato (tipo, versione se nota, schema di connessione, strategia DDL).
### 7.3 Servizi di autenticazione e autorizzazione

## 8. Requisiti non funzionali tecnici
### 8.1 Prestazioni e scalabilità
### 8.2 Logging e monitoraggio
Descrivi la strategia di logging rilevata (framework, livelli, output).
### 8.3 Gestione errori
Descrivi il pattern di error handling (exception handler globale, @ControllerAdvice, middleware, ecc.).
### 8.4 Testing
Descrivi i test rilevati (unit test, integration test, framework usato, coverage se nota).

## 9. Flussi operativi — Diagrammi di sequenza
Per i 3-5 flussi principali del sistema, includi un diagramma di sequenza Mermaid:

```mermaid
sequenceDiagram
    participant Client
    participant Controller
    participant Service
    participant Repository
    participant DB

    Client->>Controller: GET /api/risorsa/{{id}}
    Controller->>Service: findById(id)
    Service->>Repository: findById(id)
    Repository->>DB: SELECT ...
    DB-->>Repository: ResultSet
    Repository-->>Service: Optional<Entita>
    alt Entità trovata
        Service-->>Controller: Entita
        Controller-->>Client: 200 OK + JSON
    else Non trovata
        Service-->>Controller: throws NotFoundException
        Controller-->>Client: 404 Not Found
    end
```
Adatta con i flussi reali rilevati dal codice. Includi sempre il flusso di errore (alt/else).

## 10. Flussi asincroni e integrazioni event-driven
(Includi solo se il sistema usa code, pub/sub, webhook, event bus)

Per ogni flusso:
### 10.x [Nome flusso]
- **Direzione**: in ingresso / in uscita
- **Canale/coda/topic**: nome
- **Produttore**: componente che invia
- **Consumatore**: componente che riceve
- **Payload**: struttura del messaggio
- **Trigger**: cosa causa l'invio
- **Effetto**: cosa succede alla ricezione

```mermaid
sequenceDiagram
    participant Produttore
    participant Queue[Coda/Topic]
    participant Consumatore
    Produttore->>Queue: publish(payload)
    Queue-->>Consumatore: consume(payload)
    Consumatore->>Consumatore: elabora
```

## 11. Gestione errori e codici di stato
### 11.1 Strategia di error handling
Descrivi il pattern utilizzato (exception handler globale, error codes, circuit breaker).

### 11.2 Catalogo errori
| Codice/Eccezione | Messaggio | Contesto | HTTP Status |
|---|---|---|---|
Popola con gli errori rilevati nel codice.

## 12. Debito tecnico e osservazioni
Segnala esplicitamente (solo se rilevato nel codice):
- Configurazioni potenzialmente insicure (CORS aperti, auth disabilitabile, credenziali hardcoded)
- Bug potenziali (race condition, null pointer, risorse non chiuse)
- Debito tecnico rilevante (codice commentato, TODO/FIXME, pattern non standard)
- Differenze di comportamento tra ambienti (dev/staging/prod)

## 13. Appendici
### 13.1 Struttura del progetto
### 13.2 Script e comandi utili

---

## FASE DI REVISIONE FINALE

Dopo aver completato tutte le sezioni, esegui obbligatoriamente questa revisione:

1. **Revisione sezioni incomplete**: cerca tutte le sezioni marcate con `⚠️ Da completare`. Per ciascuna, verifica se hai trovato informazioni rilevanti leggendo i file del progetto. Se sì, completa la sezione. Se no, lascia il marker.

2. **Completezza configurazione (sezione 6)**: verifica di aver letto i file app_config (application.yml, application-dev.yml, application-prod.yml, appsettings.json). Le sezioni 6.3 (porte) e 6.4 (SLA) devono essere popolate con dati reali, non placeholder.

3. **Coerenza con la Specifica Funzionale** (se già generata): verifica che:
   - Gli endpoint nella tabella API (sezione 4.2) corrispondano ai casi d'uso della Specifica Funzionale
   - Le entità nel diagramma ER (sezione 4.3) corrispondano al modello dati funzionale
   - I ruoli di sicurezza (sezione 4.5) corrispondano agli attori descritti nella Specifica Funzionale
   - I flussi di sequenza (sezione 9) corrispondano ai flussi operativi della Specifica Funzionale

4. **Completezza diagrammi**: verifica che tutti i diagrammi Mermaid siano sintatticamente corretti. Regole Mermaid:
   - Nei `sequenceDiagram`: usa `participant` per tutti i nodi, `->>` per chiamate sincrone, `-->>` per risposte
   - Negli `erDiagram`: ogni entità deve avere almeno un campo, le relazioni usano `||--o{` ecc.
   - Nei `flowchart`: i nodi con testo speciale vanno tra virgolette `["testo"]`
   - Non usare caratteri speciali non escaped nei label (apostrofi, virgolette, parentesi)

5. **Completezza tabelle**: verifica che la tabella API (4.2) contenga tutti gli endpoint rilevati dall'analisi statica e che le tabelle in sezione 6 contengano i dati reali dai file di configurazione.

Se trovi incoerenze, correggile direttamente nel documento prima di consegnare.
"""


SYSTEM_ARCHITECTURE_DOC = """Genera il Documento di Architettura di Sistema per il progetto "{project_name}",
composto da più microservizi.

## Analisi statica del progetto complessivo
{static_analysis}

## Riepiloghi dei singoli microservizi
{service_summaries}

## Istruzioni
Produci un documento Markdown professionale seguendo ESATTAMENTE questa struttura.
L'obiettivo è descrivere come i microservizi collaborano tra loro — NON ripetere i dettagli interni di ciascuno.

Per le sezioni senza dati sufficienti scrivi:
`> ⚠️ Da completare — informazioni non rilevabili dal codice sorgente in questa fase.`

---

# Architettura di Sistema — {project_name}

## 1. Introduzione
### 1.1 Scopo del documento
Questo documento descrive l'architettura complessiva del sistema, le integrazioni tra i microservizi e i flussi operativi end-to-end.
### 1.2 Panoramica del sistema
Descrizione di alto livello: cosa fa il sistema, per chi, in quale contesto.
### 1.3 Limitazioni note
Funzionalità non ancora implementate o fuori scope, deducibili dal codice.

## 2. Vincoli architetturali
Documenta i vincoli non negoziabili che hanno guidato le scelte architetturali.

### 2.1 Vincoli tecnologici
| Vincolo | Valore/Versione | Fonte |
|---------|-----------------|-------|
Cerca in: pom.xml (java.version, spring-boot.version), Dockerfile (FROM image), build.gradle, .csproj (TargetFramework).

### 2.2 Vincoli organizzativi e normativi
Documenta eventuali vincoli normativi (GDPR, normative PA, standard di sicurezza) deducibili dal codice (es. presenza di audit log, cifratura dati, gestione consenso).

### 2.3 Vincoli infrastrutturali
Ambienti di deployment, container, cloud provider, se deducibili dalla configurazione.

## 3. Mappa dei microservizi
### 3.1 Elenco microservizi
| Microservizio | Responsabilità | Tecnologia | Database | Porta |
|---|---|---|---|---|

### 3.2 Diagramma architetturale
```mermaid
flowchart TD
    Client[Client / Browser] --> GW[API Gateway / Frontend]
    subgraph Backend
        GW --> SvcA[Microservizio A]
        GW --> SvcB[Microservizio B]
        SvcA --> DBA[(DB A)]
        SvcB --> DBB[(DB B)]
        SvcA -->|REST| SvcB
    end
```
Adatta con i microservizi reali, le loro comunicazioni (REST, messaggi) e i database. Usa le porte reali dai file di configurazione.

## 4. Integrazioni e comunicazioni
### 4.1 Matrice di dipendenza
| Servizio chiamante | Servizio chiamato | Tipo (REST/async/event) | Endpoint/Topic | Scopo |
|---|---|---|---|---|

### 4.2 Pattern di comunicazione
Descrivi i pattern utilizzati: REST sincrono, code messaggi, event-driven, ecc.

### 4.3 Autenticazione e sicurezza cross-service
Come si autenticano i servizi tra loro (JWT, API key, OAuth2, ecc.) e come vengono propagate le identità.

## 5. Flussi operativi end-to-end
Descrivi i 3-5 flussi principali del sistema dal punto di vista dell'utente, mostrando la sequenza di microservizi coinvolti.

Per ogni flusso includi un diagramma di sequenza:
```mermaid
sequenceDiagram
    participant U as Utente
    participant FE as Frontend
    participant SvcA as Microservizio A
    participant SvcB as Microservizio B
    participant DB as Database

    U->>FE: Azione utente
    FE->>SvcA: POST /api/risorsa
    SvcA->>SvcB: GET /api/dipendenza
    SvcB-->>SvcA: risposta
    SvcA->>DB: INSERT
    DB-->>SvcA: OK
    SvcA-->>FE: 201 Created
    FE-->>U: Conferma
```

## 6. Modello dati complessivo
### 6.1 Database per servizio
| Microservizio | Tipo DB | Database/Schema | Entità principali |
|---|---|---|---|

### 6.2 Relazioni cross-service
Descrivi come le entità di servizi diversi si riferiscono tra loro (ID condivisi, eventual consistency, saga pattern).

### 6.3 Diagramma ER di sistema
```mermaid
erDiagram
    ENTITA_SERVIZIO_A {
        Long id PK
        String campo1
    }
    ENTITA_SERVIZIO_B {
        Long id PK
        Long entitaAId FK
    }
    ENTITA_SERVIZIO_A ||--o{ ENTITA_SERVIZIO_B : "riferimento logico"
```
Mostra le entità principali di tutti i servizi e le relazioni logiche tra esse.

## 7. Stack tecnologico unificato
| Tecnologia | Versione | Usata da | Scopo |
|---|---|---|---|

## 8. Deployment e infrastruttura
### 8.1 Architettura di deployment
```mermaid
flowchart TD
    subgraph Host/Container
        SvcA[Microservizio A :8080]
        SvcB[Microservizio B :8081]
        DB[(Database)]
    end
    Internet --> SvcA
    Internet --> SvcB
```
Usa le porte reali dai file application.yml/appsettings.json di ogni microservizio.
### 8.2 Configurazione condivisa
Variabili d'ambiente condivise, config server, service discovery, load balancer.

## 9. Decisioni architetturali
Documenta le 3-5 decisioni architetturali principali deducibili dal codice. Per ogni decisione:

### DA-001: [Titolo decisione]
- **Contesto**: problema che la decisione risolve
- **Decisione**: cosa è stato scelto e come è implementato
- **Conseguenze**: vantaggi e svantaggi di questa scelta
- **Evidenza nel codice**: dove si vede questa decisione (classe/file/pattern)

Esempi di decisioni deducibili: scelta JWT vs session, pattern Repository, uso di code async, separazione microservizi, strategia DDL (create-drop vs validate), framework di sicurezza.

## 10. Crosscutting concepts
Aspetti trasversali a tutti i microservizi (arc42 §8):

### 10.1 Autenticazione e autorizzazione
Come JWT/token viene generato, validato e propagato tra i servizi. Ruoli e permessi condivisi.

### 10.2 Logging e monitoraggio
Framework di logging usato, formato dei log, aggregazione centralizzata se presente.

### 10.3 Error handling trasversale
Pattern comuni di gestione errori tra i servizi (codici di errore condivisi, formato risposta di errore standard).

### 10.4 Gestione della configurazione
Come vengono gestite le configurazioni per ambiente (config server, variabili d'ambiente, profili Spring/appsettings).

### 10.5 Sicurezza trasversale
CORS, CSRF, rate limiting, validazione input — pattern comuni a tutti i servizi.

## 11. Requisiti non funzionali trasversali
### 11.1 Scalabilità
### 11.2 Resilienza e fault tolerance
### 11.3 Logging e monitoraggio centralizzato
### 11.4 Strategia di testing (integration test cross-service)

## 12. Matrice microservizio-funzionalità
| Funzionalità business | Microservizio responsabile | Microservizi coinvolti | Note |
|---|---|---|---|

---

## FASE DI REVISIONE FINALE

Dopo aver completato tutte le sezioni, esegui obbligatoriamente questa revisione:

1. **Revisione sezioni incomplete**: cerca tutte le sezioni marcate con `⚠️ Da completare`. Per ciascuna, verifica se hai trovato informazioni nei riepiloghi dei microservizi. Se sì, completa la sezione.

2. **Completezza vincoli (sezione 2)**: verifica di aver documentato i vincoli tecnologici reali (versioni Java/framework dai pom.xml, immagini Docker, ecc.).

3. **Completezza decisioni architetturali (sezione 9)**: verifica di aver documentato almeno 3 decisioni architetturali deducibili dal codice. Se non ne trovi, cerca: pattern di autenticazione, strategia di persistenza, pattern di comunicazione tra servizi, scelte di framework.

4. **Completezza crosscutting (sezione 10)**: verifica che le sezioni 10.1-10.5 siano popolate con informazioni reali dal codice, non placeholder.

5. **Coerenza con le specifiche per-servizio** (se già generate): verifica che:
   - La matrice di dipendenza (sezione 4.1) sia coerente con gli endpoint esposti da ciascun microservizio
   - Il diagramma ER di sistema (sezione 6.3) includa tutte le entità principali descritte nelle specifiche tecniche per-servizio
   - I flussi end-to-end (sezione 5) siano coerenti con i casi d'uso delle specifiche funzionali per-servizio
   - Le porte nel diagramma deployment (sezione 8.1) corrispondano ai valori reali nei file di configurazione

6. **Completezza diagrammi Mermaid**: verifica la sintassi di tutti i diagrammi prima di consegnare.

Se trovi incoerenze, correggile direttamente nel documento.
"""


SERVICE_SUMMARY = """Genera un riepilogo sintetico del microservizio "{service_name}" per il documento di architettura di sistema.

## Analisi dettagliata dei moduli
{module_analyses}

## Istruzioni
Produci un riepilogo SINTETICO con ESATTAMENTE queste sezioni (massimo 3 righe per sezione):

1. **Responsabilità**: cosa fa questo microservizio (2-3 frasi)
2. **API esposte**: lista degli endpoint principali (metodo + path + descrizione breve, max 10)
3. **Entità gestite**: nomi delle entità con i campi chiave (max 5 entità)
4. **Dipendenze esterne**: altri servizi o sistemi che chiama (nome + tipo di comunicazione)
5. **Tecnologie specifiche**: DB, librerie particolari, protocolli (non ripetere lo stack comune)
6. **Note**: pattern rilevanti, criticità, particolarità importanti per l'integrazione

NON dilungarti nei dettagli implementativi. Questo riepilogo serve esclusivamente per capire il ruolo del servizio nel sistema complessivo e le sue interfacce verso l'esterno.
"""
