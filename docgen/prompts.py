"""Template prompt in italiano per le chiamate Claude API."""

SYSTEM_PROMPT = """Sei un analista software senior specializzato in progetti IT.

Regole:
- L'output deve essere SEMPRE in Markdown strutturato e in lingua italiana.
- Non inventare funzionalità o dettagli non presenti nel codice sorgente.
- Usa terminologia tecnica italiana (es. "endpoint", "entità", "componente", "servizio").
- Se una sezione non ha dati sufficienti, scrivi: "Da completare — informazioni non rilevabili dal codice sorgente".
- Sii preciso e professionale. Il documento sarà usato in contesti istituzionali.
- Non aggiungere disclaimer o note sulla natura AI del documento.
"""


ANALYZE_CHUNK = """Analizza il seguente modulo di codice sorgente ed estrai le informazioni strutturate richieste.

## Contesto progetto
Nome progetto: {project_name}
{static_analysis}

## Codice sorgente del modulo
{chunk_content}

## Istruzioni
Analizza il codice sopra e produci un report strutturato con ESATTAMENTE queste sezioni:

### 1. Scopo del modulo
Descrivi brevemente lo scopo e la responsabilità di questo modulo nel contesto del progetto.

### 2. Funzionalità principali
Lista le funzionalità implementate in questo modulo (operazioni CRUD, logiche di business, ecc.).

### 3. Componenti chiave
Per ogni file significativo, descrivi il suo ruolo:
- Nome file, tipo (Controller/Service/Entity/Component/ecc.), responsabilità

### 4. Flussi operativi
Descrivi i flussi principali (es. "L'utente richiede GET /api/utenti → Controller → Service → Repository → risposta JSON").

### 5. Modello dati
Se sono presenti entità/modelli, descrivi le entità con i loro attributi e relazioni.

### 6. Interfaccia utente
Se sono presenti componenti frontend, descrivi le viste e le interazioni utente.

### 7. Regole di business e vincoli
Identifica e documenta OGNI regola di business implementata nel codice:
- Vincoli di validazione (cosa viene rifiutato e perché)
- Vincoli di relazione tra entità (incompatibilità, obbligatorietà condizionale)
- Comportamenti condizionali basati su stato, configurazione o ambiente
- Logica di cascata (cosa succede quando si elimina/modifica un'entità)
- Idempotenza e gestione duplicati
Per ogni regola indica: dove è implementata (classe/metodo), cosa succede se il vincolo è violato (eccezione, codice errore), e se è documentata o implicita.

### 8. Flussi asincroni e integrazioni event-driven
Se il modulo produce o consuma messaggi/eventi (queue, pub/sub, webhook, signal, event bus), documenta per ciascuno:
- Direzione (in ingresso / in uscita)
- Canale/coda/topic
- Payload (struttura del messaggio)
- Trigger (cosa causa l'invio/ricezione)
- Effetto (cosa succede alla ricezione)

### 9. Gestione errori e messaggi
Elenca i codici/messaggi di errore definiti nel codice, con:
- Costante o codice identificativo
- Messaggio utente
- Contesto di utilizzo (quando viene lanciato)
- HTTP status associato (se applicabile)

### 10. Criticità e osservazioni tecniche
Segnala esplicitamente:
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
Produci un documento Markdown professionale con ESATTAMENTE questa struttura:

# Specifica Funzionale — {project_name}

## 1. Introduzione
### 1.1 Scopo del documento
### 1.2 Ambito del sistema
### 1.3 Riferimenti
### 1.4 Glossario

## 2. Descrizione generale del sistema
### 2.1 Panoramica
### 2.2 Utenti e attori del sistema
### 2.3 Vincoli e assunzioni

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
Per ogni caso d'uso PRINCIPALE (che modifica lo stato del sistema):
### UC-001: [Titolo]
- **Attore**: chi inizia l'azione
- **Precondizioni**: stato del sistema prima
- **Flusso principale**: sequenza numerata di passi
- **Flussi alternativi**: OBBLIGATORIO — almeno 1 flusso alternativo per caso d'uso (validazione fallita, dato non trovato, permessi insufficienti, conflitto, timeout, ecc.)
- **Eccezioni**: condizioni di errore e comportamento del sistema (codice errore, messaggio)
- **Postcondizioni**: stato del sistema dopo l'operazione

Non produrre casi d'uso triviali (es. "l'utente apre la pagina"). Concentrati su operazioni significative.

## 5. Modello dati funzionale
Descrivi le entità dal punto di vista funzionale (non tecnico), le relazioni tra esse, e includi un diagramma Mermaid erDiagram.

## 6. Interfaccia utente
Descrivi le schermate principali e i flussi di navigazione. Includi un diagramma Mermaid del flusso di navigazione se possibile.

## 7. Integrazioni e interfacce esterne
Descrivi le integrazioni con sistemi esterni, API consumate, ecc.

## 8. Regole di business
Catalogo delle regole di business estratte dal codice, in formato:
### RB-001: [Nome regola]
- **Descrizione**: cosa impone la regola
- **Implementazione**: dove è implementata (classe, metodo)
- **Vincolo**: cosa succede se la regola è violata (eccezione, errore, blocco)
- **Impatto**: quali operazioni/casi d'uso sono influenzati

Includi: validazioni, vincoli di relazione tra entità, comportamenti condizionali basati su stato/config, logiche di cascata, idempotenza.

## 9. Requisiti non funzionali
### 9.1 Prestazioni
### 9.2 Sicurezza
### 9.3 Usabilità
### 9.4 Disponibilità

## 10. Appendici
### 10.1 Matrice funzionalità-componenti
Crea una tabella che mappa ogni requisito funzionale ai componenti che lo implementano.

IMPORTANTE: Se una sezione non ha dati sufficienti dal codice analizzato, scrivi "Da completare — informazioni non rilevabili dal codice sorgente" e NON inventare contenuti.
"""


TECHNICAL_DOC = """Genera il Documento di Specifica Tecnica completo per il progetto "{project_name}".

## Analisi statica del progetto
{static_analysis}

## Analisi dettagliate dei moduli
{module_analyses}

## Istruzioni
Produci un documento Markdown professionale con ESATTAMENTE questa struttura:

# Specifica Tecnica — {project_name}

## 1. Introduzione
### 1.1 Scopo del documento
### 1.2 Ambito del sistema
### 1.3 Riferimenti
### 1.4 Glossario tecnico

## 2. Architettura del sistema
### 2.1 Architettura generale
Includi un diagramma Mermaid dell'architettura (flowchart o C4).
### 2.2 Pattern architetturali
### 2.3 Diagramma dei componenti
Includi un diagramma Mermaid dei componenti e le loro interazioni.

## 3. Stack tecnologico
Elenca tutte le tecnologie rilevate con versione:
| Tecnologia | Versione | Scopo |
|---|---|---|

## 4. Dettaglio backend
### 4.1 Struttura dei package
### 4.2 API REST
Includi una tabella completa:
| Metodo | Endpoint | Descrizione | Controller |
|---|---|---|---|
### 4.3 Modello dati
Includi il diagramma ER Mermaid con tutti i campi e le relazioni.
### 4.4 Logica di business
### 4.5 Sicurezza e autenticazione

## 5. Dettaglio frontend
### 5.1 Struttura dei moduli
### 5.2 Routing
### 5.3 Componenti principali
### 5.4 Servizi e comunicazione con il backend
### 5.5 Gestione dello stato

## 6. Configurazione e deployment
### 6.1 Configurazione applicativa
### 6.2 Requisiti di sistema
### 6.3 Istruzioni di build e deploy
### 6.4 Variabili d'ambiente

## 7. Integrazioni esterne
### 7.1 API consumate
### 7.2 Database
### 7.3 Servizi di autenticazione

## 8. Requisiti non funzionali tecnici
### 8.1 Prestazioni e scalabilità
### 8.2 Logging e monitoraggio
### 8.3 Gestione errori
### 8.4 Testing

## 9. Flussi asincroni e integrazioni event-driven
Se il sistema produce o consuma messaggi/eventi (code, pub/sub, webhook, signal, event bus), documenta per ciascuno:
### 9.x [Nome flusso]
- **Direzione**: in ingresso / in uscita
- **Canale/coda/topic**: nome del canale
- **Produttore**: componente che invia
- **Consumatore**: componente che riceve
- **Payload**: struttura del messaggio
- **Trigger**: cosa causa l'invio
- **Effetto**: cosa succede alla ricezione
Includi un diagramma Mermaid (sequenceDiagram) per i flussi asincroni più complessi.

## 10. Gestione errori e codici di stato
### 10.1 Strategia di error handling
Pattern utilizzati (exception handler globale, error codes, circuit breaker).
### 10.2 Catalogo errori
| Codice | Messaggio | Contesto | HTTP Status |
|---|---|---|---|

## 11. Debito tecnico e osservazioni
Segnala esplicitamente:
- Configurazioni potenzialmente insicure (CORS aperti, auth disabilitabile, credenziali hardcoded)
- Bug potenziali (race condition, null pointer, risorse non chiuse)
- Debito tecnico rilevante (codice commentato, TODO/FIXME, pattern non standard)
- Differenze di comportamento tra ambienti (dev/staging/prod)

## 12. Appendici
### 12.1 Struttura del progetto
### 12.2 Script e comandi utili

IMPORTANTE: Se una sezione non ha dati sufficienti dal codice analizzato, scrivi "Da completare — informazioni non rilevabili dal codice sorgente" e NON inventare contenuti. Usa i dati dell'analisi statica per popolare le tabelle API e le entità.
"""


SYSTEM_ARCHITECTURE_DOC = """Genera il Documento di Architettura di Sistema per il progetto "{project_name}",
che è composto da più microservizi.

## Analisi statica del progetto complessivo
{static_analysis}

## Riepiloghi dei singoli microservizi
{service_summaries}

## Istruzioni
Produci un documento Markdown professionale con ESATTAMENTE questa struttura.
L'obiettivo è descrivere come i microservizi collaborano tra loro, NON ripetere i dettagli interni di ciascuno.

# Architettura di Sistema — {project_name}

## 1. Introduzione
### 1.1 Scopo del documento
Questo documento descrive l'architettura complessiva del sistema, le integrazioni tra i microservizi e i flussi operativi end-to-end.
### 1.2 Panoramica del sistema
Descrizione di alto livello: cosa fa il sistema, per chi, in quale contesto (se si capisce).

## 2. Mappa dei microservizi
### 2.1 Elenco microservizi
Per ogni microservizio, una riga in tabella:
| Microservizio | Responsabilità | Tecnologia | Database | Porta |
|---|---|---|---|---|
### 2.2 Diagramma architetturale
Includi un diagramma Mermaid (flowchart) che mostra tutti i microservizi, il frontend e le comunicazioni tra di essi (REST, messaggi, ecc.).

## 3. Integrazioni e comunicazioni
### 3.1 Matrice di dipendenza
Tabella che mostra chi chiama chi:
| Servizio chiamante | Servizio chiamato | Tipo (REST/async) | Endpoint/Topic |
|---|---|---|---|
### 3.2 Pattern di comunicazione
Descrivi i pattern utilizzati: REST sincrono, code messaggi, event-driven, ecc.
### 3.3 Autenticazione e sicurezza cross-service
Come si autenticano i servizi tra loro (JWT, API key, OAuth2, ecc.).

## 4. Flussi operativi end-to-end
Descrivi i 3-5 flussi principali del sistema dal punto di vista dell'utente, mostrando quali microservizi vengono coinvolti in sequenza. Per ogni flusso includi un diagramma Mermaid (sequenceDiagram).

## 5. Modello dati complessivo
### 5.1 Database per servizio
| Microservizio | Tipo DB | Database | Entità principali |
|---|---|---|---|
### 5.2 Relazioni cross-service
Descrivi come le entità di servizi diversi si riferiscono tra loro (es. ID condivisi, eventual consistency).
### 5.3 Diagramma ER di sistema
Includi un diagramma Mermaid erDiagram che mostra le entità principali di tutti i servizi e le relazioni logiche tra esse.

## 6. Stack tecnologico unificato
| Tecnologia | Versione | Usata da | Scopo |
|---|---|---|---|

## 7. Deployment e infrastruttura
### 7.1 Architettura di deployment
Diagramma Mermaid del deployment (container, server, rete).
### 7.2 Configurazione condivisa
Variabili d'ambiente, config server, service discovery.

## 8. Requisiti non funzionali trasversali
### 8.1 Scalabilità
### 8.2 Resilienza e fault tolerance
### 8.3 Logging e monitoraggio centralizzato
### 8.4 Strategia di testing (integration test cross-service)

## 9. Appendici
### 9.1 Matrice microservizio-funzionalità
Tabella che mappa le funzionalità business ai microservizi che le implementano.

IMPORTANTE: Se una sezione non ha dati sufficienti, scrivi "Da completare — informazioni non rilevabili dal codice sorgente" e NON inventare contenuti. Concentrati sulle INTEGRAZIONI tra servizi, non sui dettagli interni.
"""


SERVICE_SUMMARY = """Genera un riepilogo sintetico del microservizio "{service_name}" per il contesto del documento di architettura di sistema.

## Analisi dettagliata dei moduli
{module_analyses}

## Istruzioni
Produci un riepilogo SINTETICO (max 500 parole) con:

1. **Responsabilità**: cosa fa questo microservizio (2-3 frasi)
2. **API esposte**: lista degli endpoint principali (metodo + path + descrizione breve)
3. **Entità gestite**: nomi delle entità con campi chiave
4. **Dipendenze esterne**: altri servizi o sistemi che chiama
5. **Tecnologie specifiche**: DB, librerie particolari, protocolli
6. **Note**: pattern rilevanti, criticità, particolarità

NON dilungarti nei dettagli implementativi. Questo riepilogo serve per capire il ruolo del servizio nel sistema complessivo.
"""
