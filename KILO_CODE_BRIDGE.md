# Istruzioni per Kilo Code — Modalità LLM Bridge

## Come funziona

DocGen ha una modalità `--llm-bridge` che delega le chiamate LLM a un agente esterno (tu, Kilo Code).

Lo script Python fa tutta l'analisi del codice sorgente (gratis), poi per ogni chiamata LLM:
1. Scrive il prompt in `<progetto>/DocGen/.bridge/prompt_NNN.md`
2. Crea un file segnale `READY`
3. Si mette in pausa, in attesa della risposta
4. Tu leggi il prompt, lo processi, e salvi la risposta in `response_NNN.md`
5. Lo script rileva la risposta e prosegue automaticamente

## Prompt da dare a Kilo Code

Copia e incolla questo prompt in Kilo Code PRIMA di lanciare lo script:

---

```
Devi agire come bridge LLM per lo script DocGen. Ecco cosa devi fare:

1. Lancia nel terminale:
   cd /path/to/progetto-da-analizzare
   python3 -m docgen . --llm-bridge

2. Lo script creerà la cartella DocGen/.bridge/ nel progetto.
   Quando lo script scrive un prompt e crea il file READY, tu devi:

   a. Leggere il file DocGen/.bridge/system_prompt.md (solo la prima volta, è il contesto di sistema)
   b. Leggere il file DocGen/.bridge/READY per sapere quale prompt processare
   c. Leggere il file prompt indicato (es. DocGen/.bridge/prompt_001.md)
   d. Processare il prompt con il tuo LLM usando il system prompt come contesto
   e. Salvare la risposta COMPLETA in DocGen/.bridge/response_001.md (stesso numero del prompt)

3. Ripeti per ogni prompt fino a quando lo script non termina.

IMPORTANTE:
- Il file response deve avere lo STESSO numero del prompt (prompt_001 → response_001)
- Scrivi SOLO il contenuto della risposta nel file, senza wrapper o commenti tuoi
- Aspetta che compaia il file READY prima di processare il prossimo prompt
- Il system_prompt.md va usato come contesto di sistema per TUTTE le chiamate

Il progetto da analizzare è: [INSERISCI PATH O NOME PROGETTO]
```

---

## Passi operativi

### 1. Apri il progetto target in VS Code

### 2. Apri Kilo Code e incolla il prompt sopra

### 3. Kilo Code lancerà lo script e gestirà automaticamente il ciclo prompt/risposta

### 4. Al termine, troverai i documenti generati in `<progetto>/DocGen/`

## Comando manuale (senza Kilo Code)

Se vuoi lanciare lo script a mano e usare Kilo Code solo per le risposte:

```bash
# Terminale 1: lancia lo script
cd /path/to/progetto
python3 -m docgen . --llm-bridge

# Poi in Kilo Code, chiedi:
# "Leggi il file DocGen/.bridge/READY, processa il prompt indicato,
#  e salva la risposta nel file response corrispondente"
```

## Note tecniche

- La directory `.bridge/` viene creata dentro `DocGen/` (che è nella root del progetto analizzato)
- I file sono numerati sequenzialmente: `prompt_001.md`, `prompt_002.md`, ecc.
- Lo script fa polling ogni 2 secondi per verificare la presenza della risposta
- Se lo script non riceve risposta, rimane in attesa indefinitamente (puoi interrompere con Ctrl+C)
- I token vengono stimati approssimativamente (non c'è conteggio reale come con l'API)
