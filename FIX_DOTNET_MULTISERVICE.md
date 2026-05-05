# Fix: Supporto .NET Multi-Solution in DocGen

## Contesto

DocGen funziona correttamente per progetti Java/Spring Boot multi-modulo (ogni directory con `pom.xml` diventa un modulo). Per progetti .NET con architettura multi-repository/multi-solution, invece, **tutti i file vengono raggruppati in un unico modulo "backend"**, producendo un solo `docgen_context.md` invece di documentazione separata per ogni microservizio.

## Decisione di Design

**Granularità modulo = repository (livello 1)**. Ogni directory di primo livello che contiene un `.sln` è un modulo. Le singole sub-API (`.csproj`) dentro il repo NON sono moduli separati, ma saranno sezioni interne nella documentazione del modulo.

---

## Struttura del progetto .NET di riferimento

Il progetto di test è in `test-capitanerie/` e contiene 2 repository:

```
cartella-padre/                              ← project_root passato a docgen
├── cdp.itaca.api.anagrafica/                ← Livello 1: REPO → MODULO (.sln qui)
│   ├── ITACA.Api.Anagrafica.sln
│   ├── ITACA.Api.Anagrafica.Allergia/       ← Sub-API (.csproj, Controllers/, Dockerfile)
│   ├── ITACA.Api.Anagrafica.Persona/        ← Sub-API (.csproj, Controllers/, Dockerfile)
│   ├── ITACA.Api.Anagrafica.Facade/         ← Sub-API (orchestratore)
│   └── ... (16 sub-API totali)
├── cdp.itaca.api.avanzamento/               ← Livello 1: REPO → MODULO (.sln qui)
│   ├── ITACA.Api.Avanzamento.sln
│   ├── ITACA.Api.Avanzamento/               ← Sub-API
│   ├── ITACA.Api.Avanzamento.Facade/        ← Sub-API
│   └── ... (5 sub-API totali)
```

Ogni sub-API è un microservizio .NET 6.0 indipendente con:
- `.csproj` (Microsoft.NET.Sdk.Web)
- `Controllers/` con `[ApiController]`, `[HttpGet]`, ecc.
- `Services/` + `Interfaces/`
- `Database/` con repository MongoDB (`IMongoCollection`, `MongoClient`)
- `Models/` con `BsonElement`, `BsonDateTimeOptions`
- `Dockerfile` + `appsettings.json`
- Pipeline CI/CD dedicate (azure-pipelines-*.yml)

---

## Root Cause — Perché .NET fallisce

### Flusso attuale in `_detect_module()` (scanner.py:320-362)

Per il file `cdp.itaca.api.anagrafica\ITACA.Api.Anagrafica.Allergia\Controllers\AllergiaController.cs`:

1. `parts[0]` = `cdp.itaca.api.anagrafica`
2. **Riga 342**: cerca `pom.xml` in `cdp.itaca.api.anagrafica/` → no
3. **Riga 349-350**: cerca `*.csproj` in `cdp.itaca.api.anagrafica/` → **NO** (i `.csproj` sono un livello sotto, nelle sub-directory!)
4. **Riga 357**: fallback estensione `.cs` → ritorna `"backend"`
5. **Tutti i file** → modulo `"backend"` → 1 solo modulo → modalità progetto singolo

### Perché Java funziona

```
cartella-padre/
├── microservizio-admin/     ← pom.xml È QUI (livello 1) ✓ → riga 342 lo trova
│   └── src/main/java/...
```

In Java `pom.xml` è al livello 1. In .NET `.csproj` è al livello 2, ma `.sln` è al livello 1 e non viene cercato.

---

## Fix da implementare

### FIX 1 — Detection modulo via `.sln` (CRITICO)

**File**: `docgen/scanner.py`, funzione `_detect_module()`, righe 345-351

Aggiungere un check per `.sln` nella directory di primo livello, **PRIMA** del check `.csproj` esistente.

Il codice attuale (righe 339-351):
```python
    # Multi-module Maven: cerca pom.xml nella prima directory
    if len(parts) > 1:
        first_dir = os.path.join(project_root, parts[0])
        if os.path.isfile(os.path.join(first_dir, "pom.xml")):
            return parts[0]

    # Multi-project .NET: cerca .csproj nella prima directory
    if len(parts) > 1:
        first_dir = os.path.join(project_root, parts[0])
        if os.path.isdir(first_dir):
            for f in os.listdir(first_dir):
                if f.endswith(".csproj"):
                    return parts[0]
```

Deve diventare:
```python
    # Multi-module Maven: cerca pom.xml nella prima directory
    if len(parts) > 1:
        first_dir = os.path.join(project_root, parts[0])
        if os.path.isfile(os.path.join(first_dir, "pom.xml")):
            return parts[0]

    # Multi-solution .NET: cerca .sln nella prima directory (modulo = repo)
    if len(parts) > 1:
        first_dir = os.path.join(project_root, parts[0])
        if os.path.isdir(first_dir):
            for f in os.listdir(first_dir):
                if f.endswith(".sln"):
                    return parts[0]

    # Multi-project .NET: cerca .csproj nella prima directory (singola solution)
    if len(parts) > 1:
        first_dir = os.path.join(project_root, parts[0])
        if os.path.isdir(first_dir):
            for f in os.listdir(first_dir):
                if f.endswith(".csproj"):
                    return parts[0]
```

Il check `.sln` DEVE venire PRIMA del check `.csproj`. Così:
- Multi-repo con `.sln` al livello 1 → modulo = directory repo ✓
- Singola solution con `.csproj` al livello 1 → continua a funzionare come prima ✓

---

### FIX 2 — Abbassare soglia `LARGE_PROJECT_MIN_MODULES` (MEDIO)

**File**: `docgen/config.py`, riga 63

Cambiare:
```python
LARGE_PROJECT_MIN_MODULES = 3   # Moduli minimi per considerarlo "grande"
```

In:
```python
LARGE_PROJECT_MIN_MODULES = 2   # Moduli minimi per considerarlo "grande"
```

Senza questo fix, anche con detection corretta, 2 repository non attiverebbero la modalità multi-microservizio (`n_modules = 2 < 3`).

---

### FIX 3a — Classificazione file: aggiungere pattern MongoDB e Service (MEDIO)

**File**: `docgen/scanner.py`, funzione `_classify_file()`, righe 266-287 (blocco `if extension == ".cs" and content:`)

Il blocco attuale classifica solo: migration, middleware, DbContext, [ApiController], ControllerBase, IXxxService, [Table]/[Key].

Aggiungere **dopo** il check `[Table(` / `[Key]` (riga 286-287):

```python
        # Entity/Model con EF Core annotation
        if "[Table(" in content or "[Key]" in content:
            return "entity"
        # Entity/Model MongoDB (BsonElement, BsonId)
        if "BsonElement" in content or "BsonId" in content:
            return "entity"
        # Repository MongoDB
        if "IMongoCollection" in content or "IMongoDatabase" in content:
            return "repository"
        # Classi Service (non solo interfacce)
        if re.search(r'class\s+\w+Service\b', content):
            return "service"
```

---

### FIX 3b — Estrazione entità MongoDB (MEDIO)

**File**: `docgen/analyzer.py`

Aggiungere una nuova funzione `_extract_mongodb_entity()` per estrarre modelli MongoDB. Pattern nel progetto reale (da `AllergiaModel.cs`):

```csharp
using MongoDB.Bson.Serialization.Attributes;

public class AllergiaModel
{
    public int Id { get; set; }

    [Required(ErrorMessage = "Campo Obbligatorio")]
    [MaxLength(50, ErrorMessage = "...")]
    public string DescrizioneBreve { get; set; }

    [BsonElement]
    [BsonDateTimeOptions(Kind = DateTimeKind.Local)]
    public DateTime DataInizioValidita { get; set; }
}
```

La funzione deve:
1. Trovare il nome della classe (`public class XxxModel`)
2. Estrarre le proprietà pubbliche con `public {tipo} {nome} { get; set; }`
3. Annotare `[Required]`, `[MaxLength]`, `[BsonElement]`, `[BsonId]`
4. Ritornare un oggetto `JpaEntity` (stesso tipo usato per EF Core)

Poi nel ciclo `analyze_project()`, il blocco attuale per le entità .cs (righe 990-995) deve provare prima EF Core, poi MongoDB come fallback:

```python
        # Entità C# (EF Core o MongoDB)
        if file.category == "entity" and file.extension == ".cs":
            entity = _extract_dotnet_entity(file)
            if not entity:
                entity = _extract_mongodb_entity(file)
            if entity and entity.name not in seen_entities:
                analysis.entities.append(entity)
                seen_entities.add(entity.name)
```

---

### FIX 4 — Classificare Startup.cs e Program.cs come config (BASSO)

**File**: `docgen/scanner.py`, funzione `_classify_file()`, nel blocco `if extension == ".cs" and content:` (riga 267)

Aggiungere **all'inizio** del blocco (prima del check Migrations, riga 269):

```python
        # Startup / Program — configurazione applicazione
        if basename in ("startup.cs", "program.cs"):
            return "config"
```

---

### FIX 5 — Aggiungere `database.json` ai file inclusi (BASSO)

**File**: `docgen/config.py`, riga 34-42 (`INCLUDE_FILENAMES`)

Aggiungere `"database.json"` al set:

```python
INCLUDE_FILENAMES: set[str] = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ...
    "database.json",   # ← aggiungere
}
```

Il progetto usa `database.json` per la configurazione MongoDB:
```json
{
  "ConnectionStrings": {
    "Database": "ITACA",
    "Domain": "Anagrafica"
  }
}
```

---

## Riepilogo

| # | Severità | File | Cosa fare |
|---|----------|------|-----------|
| **FIX 1** | 🔴 Critico | `scanner.py:_detect_module()` | Aggiungere check `.sln` per detection modulo al livello repo |
| **FIX 2** | 🟡 Medio | `config.py:63` | `LARGE_PROJECT_MIN_MODULES = 3` → `2` |
| **FIX 3a** | 🟡 Medio | `scanner.py:_classify_file()` | Aggiungere pattern `BsonElement`, `IMongoCollection`, `class XxxService` |
| **FIX 3b** | 🟡 Medio | `analyzer.py` | Nuova funzione `_extract_mongodb_entity()` + integrazione nel ciclo |
| **FIX 4** | 🟢 Basso | `scanner.py:_classify_file()` | Classificare `Startup.cs`/`Program.cs` come config |
| **FIX 5** | 🟢 Basso | `config.py` | Aggiungere `database.json` a `INCLUDE_FILENAMES` |

## Ordine di implementazione

1. **FIX 1** (senza questo nulla funziona per .NET multi-solution)
2. **FIX 2** (necessario per attivare la modalità hybrid con pochi repo)
3. **FIX 3a** + **FIX 4** + **FIX 5** (miglioramenti classificazione, vanno insieme)
4. **FIX 3b** (estrazione entità MongoDB)

## Test di verifica

Dopo l'implementazione, lanciare:
```bash
python -m docgen ./test-capitanerie --dry-run --mode docs -n "ITACA"
```

**Risultato atteso**:
- Moduli rilevati: `cdp.itaca.api.anagrafica`, `cdp.itaca.api.avanzamento` (2 moduli, non 1 "backend")
- Modalità ibrida attivata (≥2 moduli, ≥8 chunk)
- Entità rilevate: AllergiaModel, PersonaModel, AvanzamentoModel, GradoModel, ecc.
- Endpoint rilevati: GET/POST/PUT/DELETE per ogni controller

Poi:
```bash
python -m docgen ./test-capitanerie --agent-export --mode docs -n "ITACA"
```

**Risultato atteso**:
- `docgen_instructions.md` (istruzioni generali)
- `docgen_context_cdp.itaca.api.anagrafica.md` (contesto modulo anagrafica)
- `docgen_context_cdp.itaca.api.avanzamento.md` (contesto modulo avanzamento)
- `docgen_files.json`
- `docgen_index.md`
