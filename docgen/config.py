"""Configurazione centralizzata per DocGen."""

from __future__ import annotations

from dataclasses import dataclass, field


# Rapporto caratteri/token per codice sorgente
CHARS_PER_TOKEN = 3.5

# Costi Claude Sonnet (USD per milione di token)
COST_INPUT_PER_M = 3.0
COST_OUTPUT_PER_M = 15.0

# Directory da ignorare durante la scansione
IGNORE_DIRS: set[str] = {
    ".git", "node_modules", "target", "build", "dist", "__pycache__",
    ".angular", ".gradle", ".mvn", ".idea", ".vscode", ".settings",
    "bin", "obj", "wwwroot", ".next", ".nuxt", "coverage", ".nyc_output",
    "vendor", ".tox", ".eggs", "*.egg-info", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "DocGen",
}

# Estensioni da includere
INCLUDE_EXTENSIONS: set[str] = {
    ".java", ".ts", ".html", ".xml", ".yml", ".yaml", ".properties",
    ".json", ".md", ".py", ".cs", ".cshtml", ".css", ".scss", ".sql",
    ".csproj", ".sln",
    ".js", ".go", ".rs", ".rb", ".php", ".toml",
    ".prisma",
}

# Nomi file da includere anche senza estensione classica
INCLUDE_FILENAMES: set[str] = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "Makefile", "Jenkinsfile", ".env.example",
    "appsettings.json", "appsettings.Development.json", "appsettings.Production.json",
    "launchSettings.json",
    "requirements.txt", "requirements-dev.txt", "requirements-prod.txt",
    "Pipfile", "pyproject.toml", "setup.py", "setup.cfg",
    "go.mod", "Cargo.toml", "Gemfile", "composer.json",
    "database.json",   # Configurazione MongoDB (FIX 5)
}

# Limiti
MAX_FILE_CHARS = 40_000       # Tronca file oltre questa soglia (default)

# Limiti di troncamento adattivi per categoria
TRUNCATION_LIMITS: dict[str, int] = {
    "business_critical": 80_000,
    "service": 80_000,
    "controller": 80_000,
    "entity": 40_000,
    "config": 40_000,
    "dbcontext": 40_000,
}
# Categorie non presenti usano MAX_FILE_CHARS come fallback
MAX_FILE_BYTES = 500_000      # Salta file oltre 500KB
DEFAULT_CHUNK_BUDGET = 120_000 # Token per chunk
DEFAULT_MAX_TOKENS = 200_000  # Max token contesto modello
DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Soglie per rilevamento progetto grande (multi-microservizio)
LARGE_PROJECT_MIN_MODULES = 2   # Moduli minimi per considerarlo "grande"
LARGE_PROJECT_MIN_CHUNKS = 8    # Chunk minimi per proporre la divisione


@dataclass
class DocGenConfig:
    """Configurazione completa per una sessione di generazione documentazione."""

    project_path: str = ""
    project_name: str = ""
    output_dir: str = ""
    output_format: str = "all"  # all | md | docx
    model: str = DEFAULT_MODEL
    dry_run: bool = False
    max_tokens: int = DEFAULT_MAX_TOKENS
    chunk_budget: int = DEFAULT_CHUNK_BUDGET

    export_prompts: bool = False
    llm_bridge: bool = False
    agent_export: bool = False
    mode: str = "docs"  # "docs" | "tests" | future modes

    # Filtri personalizzabili
    ignore_dirs: set[str] = field(default_factory=lambda: set(IGNORE_DIRS))
    include_extensions: set[str] = field(default_factory=lambda: set(INCLUDE_EXTENSIONS))
    include_filenames: set[str] = field(default_factory=lambda: set(INCLUDE_FILENAMES))
    max_file_chars: int = MAX_FILE_CHARS
    max_file_bytes: int = MAX_FILE_BYTES

    def chars_to_tokens(self, chars: int) -> int:
        """Stima token da caratteri."""
        return int(chars / CHARS_PER_TOKEN)

    def tokens_to_chars(self, tokens: int) -> int:
        """Stima caratteri da token."""
        return int(tokens * CHARS_PER_TOKEN)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Stima il costo in USD per una chiamata API."""
        return (
            (input_tokens / 1_000_000) * COST_INPUT_PER_M
            + (output_tokens / 1_000_000) * COST_OUTPUT_PER_M
        )
