"""Scanner del filesystem — esplora, filtra e classifica i file del progetto."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from .config import DocGenConfig

console = Console()


# ── Classificazione file ────────────────────────────────────────────────────

# Pattern path/nome per Java Spring
JAVA_CATEGORIES: list[tuple[str, str]] = [
    ("controller", "controller"),
    ("restcontroller", "controller"),
    ("resource", "controller"),
    ("service", "service"),
    ("repository", "repository"),
    ("dao", "repository"),
    ("entity", "entity"),
    ("model", "entity"),
    ("domain", "entity"),
    ("dto", "dto"),
    ("config", "config"),
    ("configuration", "config"),
    ("filter", "config"),
    ("mapper", "util"),
    ("util", "util"),
    ("helper", "util"),
    ("test", "test"),
    ("spec", "test"),
]

# Pattern per Angular (suffix del filename)
ANGULAR_SUFFIXES: list[tuple[str, str]] = [
    (".component.ts", "component"),
    (".component.html", "template"),
    (".component.css", "style"),
    (".component.scss", "style"),
    (".service.ts", "angular_service"),
    ("-routing.module.ts", "routing"),
    (".module.ts", "module"),
    (".guard.ts", "guard"),
    (".interceptor.ts", "interceptor"),
    (".pipe.ts", "pipe"),
    (".directive.ts", "directive"),
    (".resolver.ts", "resolver"),
    (".spec.ts", "test"),
]

# Annotazioni Spring per classificazione dal contenuto
SPRING_ANNOTATIONS: dict[str, str] = {
    "@RestController": "controller",
    "@Controller": "controller",
    "@Service": "service",
    "@Repository": "repository",
    "@Entity": "entity",
    "@Configuration": "config",
    "@Component": "component_spring",
}

# Attributi C# ASP.NET per classificazione dal contenuto
DOTNET_ATTRIBUTES: dict[str, str] = {
    "[ApiController]": "controller",
    ": ControllerBase": "controller",
    ": Controller": "controller",
    "DbContext": "dbcontext",
}

# ── Business-critical detection (cross-language) ────────────────────────────

# Pattern nel NOME FILE / PATH che indicano file business-critical
BUSINESS_CRITICAL_NAME_PATTERNS: list[str] = [
    # Event/Message handlers
    "listener", "consumer", "handler", "subscriber", "worker",
    "processor", "queue", "event",
    # Exception/Error handlers
    "exception", "error", "advice",
    # Cross-cutting (AOP, interceptor, decorator, guard)
    "aspect", "interceptor", "decorator", "guard", "pipe", "hook",
    # Validatori e regole business
    "validator", "rule", "policy", "constraint", "specification",
    "strategy", "state_machine", "statemachine", "workflow", "business",
    # Enum/Costanti di dominio
    "enum", "constant", "status", "error_code", "errorcode", "message",
    # Sicurezza
    "security", "auth", "cors", "csrf", "permission",
]

# Pattern nel CONTENUTO che indicano file business-critical (regex)
BUSINESS_CRITICAL_CONTENT_PATTERNS: list[str] = [
    # Event/Message handlers (Java/Spring)
    r'@RabbitListener', r'@KafkaListener', r'@SqsListener',
    r'@EventListener', r'@TransactionalEventListener',
    r'@EventHandler', r'@Subscribe',
    # Event/Message handlers (JS/TS)
    r'EventEmitter', r'addEventListener', r'on\w+Event',
    # Event/Message handlers (Python)
    r'on_message', r'signal\.connect', r'@receiver',
    # Event/Message handlers (.NET)
    r'INotificationHandler', r'IRequestHandler',
    # Exception handlers globali
    r'@ControllerAdvice', r'@ExceptionHandler',
    r'ExceptionFilter', r'ErrorBoundary',
    r'UseExceptionFilter', r'app\.use\(\s*err',
    r'exception_handler', r'error_handler',
    # AOP / Cross-cutting
    r'@Aspect', r'@Around\b', r'@Before\b', r'@After\b',
    r'@UseInterceptors', r'@UseGuards',
    # Entity lifecycle hooks
    r'@PrePersist', r'@PostUpdate', r'@PreRemove', r'@PostLoad',
    r'@EntityListeners', r'EntityListener',
    r'pre_save', r'post_save', r'pre_delete', r'post_delete',
    r'beforeCreate', r'afterUpdate', r'Model\.observe',
    # Sicurezza config
    r'configure\(HttpSecurity', r'SecurityFilterChain',
    r'UseAuthentication', r'UseAuthorization',
    r'passport\.use', r'@authorize', r'@Authorize',
    r'WebSecurityConfigurerAdapter', r'addFilterBefore',
]

# Compilati una volta sola
_BUSINESS_CRITICAL_CONTENT_RE = re.compile(
    '|'.join(BUSINESS_CRITICAL_CONTENT_PATTERNS)
)

# Priorità per categoria
PRIORITY_MAP: dict[str, str] = {
    "controller": "alta",
    "entity": "alta",
    "config": "alta",
    "routing": "alta",
    "module": "alta",
    "dbcontext": "alta",
    "business_critical": "alta",
    "middleware": "media",
    "service": "alta",
    "angular_service": "alta",
    "component": "media",
    "repository": "media",
    "dto": "media",
    "template": "bassa",
    "style": "bassa",
    "test": "bassa",
    "util": "bassa",
    "guard": "bassa",
    "interceptor": "bassa",
    "pipe": "bassa",
    "directive": "bassa",
    "resolver": "bassa",
    "component_spring": "bassa",
    "migration": "bassa",
    "altro": "bassa",
}


@dataclass
class ScannedFile:
    """Un file scansionato con metadati."""

    path: str            # Path relativo alla root del progetto
    abs_path: str        # Path assoluto
    extension: str       # .java, .ts, ecc.
    category: str        # controller, service, entity, component, ecc.
    priority: str        # alta, media, bassa
    size_bytes: int      # Dimensione in byte
    content: str = ""    # Contenuto (eventualmente troncato)
    module: str = ""     # Modulo logico (sotto-modulo Maven, es. "core", "web")
    service: str = ""    # Microservizio di appartenenza (es. "administration-api", "frontend")
    truncated: bool = False


@dataclass
class ScanResult:
    """Risultato completo della scansione."""

    files: list[ScannedFile] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)   # sotto-moduli (usati internamente per chunking)
    services: list[str] = field(default_factory=list)  # microservizi (usati per hybrid detection)
    skipped_count: int = 0
    error_count: int = 0
    total_chars: int = 0

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_size(self) -> int:
        return sum(f.size_bytes for f in self.files)

    def files_by_category(self) -> dict[str, list[ScannedFile]]:
        """Raggruppa file per categoria."""
        result: dict[str, list[ScannedFile]] = {}
        for f in self.files:
            result.setdefault(f.category, []).append(f)
        return result

    def files_by_module(self) -> dict[str, list[ScannedFile]]:
        """Raggruppa file per modulo (sotto-modulo Maven o equivalente)."""
        result: dict[str, list[ScannedFile]] = {}
        for f in self.files:
            result.setdefault(f.module or "root", []).append(f)
        return result

    def files_by_service(self) -> dict[str, list[ScannedFile]]:
        """Raggruppa file per microservizio (primo livello directory)."""
        result: dict[str, list[ScannedFile]] = {}
        for f in self.files:
            result.setdefault(f.service or f.module or "root", []).append(f)
        return result

    def top_extensions(self, n: int = 10) -> list[tuple[str, int]]:
        """Le N estensioni più frequenti."""
        counts: dict[str, int] = {}
        for f in self.files:
            counts[f.extension] = counts.get(f.extension, 0) + 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:n]


def _classify_file(rel_path: str, extension: str, content: str) -> str:
    """Classifica un file in base a path, estensione e contenuto."""
    lower_path = rel_path.lower()
    basename = os.path.basename(lower_path)

    # Config file speciali
    if basename in ("pom.xml", "build.gradle", "build.gradle.kts"):
        return "build_config"
    if basename in ("package.json",):
        return "package_config"
    if basename in ("application.yml", "application.yaml", "application.properties",
                     "application-dev.yml", "application-prod.yml"):
        return "app_config"
    if basename in ("appsettings.json", "appsettings.development.json",
                     "appsettings.production.json"):
        return "app_config"
    if basename in ("dockerfile", "docker-compose.yml", "docker-compose.yaml"):
        return "infrastructure"
    if basename in ("angular.json", "tsconfig.json", "tsconfig.app.json"):
        return "angular_config"
    if extension == ".csproj":
        return "build_config"
    if extension == ".sln":
        return "build_config"

    # Angular: controlla suffix del filename
    if extension == ".ts" or extension == ".html" or extension in (".css", ".scss"):
        # NestJS/TS business-critical patterns take priority over suffix matching
        if extension == ".ts" and content and _BUSINESS_CRITICAL_CONTENT_RE.search(content):
            return "business_critical"
        for suffix, cat in ANGULAR_SUFFIXES:
            if basename.endswith(suffix):
                return cat

    # Java: controlla annotazioni Spring nel contenuto
    if extension == ".java" and content:
        # Business-critical annotations have priority over generic Spring annotations
        if any(bc_ann in content for bc_ann in (
            "@ControllerAdvice", "@Aspect", "@RabbitListener", "@KafkaListener",
            "@JmsListener", "@EventListener", "@PreAuthorize", "@Secured",
            "SecurityFilterChain", "WebSecurityConfigurerAdapter",
        )):
            return "business_critical"
        for annotation, cat in SPRING_ANNOTATIONS.items():
            if annotation in content:
                return cat

    # C#: controlla attributi ASP.NET e pattern nel contenuto
    if extension == ".cs" and content:
        # Migrations EF Core
        if "migrations" in lower_path.split(os.sep) or "migrations" in lower_path.split("/"):
            return "migration"
        # Middleware
        if "middleware" in lower_path:
            return "middleware"
        # DbContext
        if ": DbContext" in content or ":DbContext" in content:
            return "dbcontext"
        # Controller ([ApiController] o eredita da ControllerBase/Controller)
        if "[ApiController]" in content:
            return "controller"
        if re.search(r':\s*ControllerBase\b', content) or re.search(r':\s*Controller\b', content):
            return "controller"
        # Interfacce di servizio (IXxxService)
        if re.search(r'interface\s+I\w+Service', content):
            return "service"
        # Entity/Model con EF Core annotation
        if "[Table(" in content or "[Key]" in content:
            return "entity"

    # ── Business-critical detection (cross-language) ──────────────────
    # Check per nome file/path — PRIMA di JAVA_CATEGORIES per evitare
    # che pattern generici come "util" catturino file come StatusEnum.java.
    # Ma se il path matcha un JAVA_CATEGORIES noto, rispetta quello:
    # es. src/main/controller/FooHandler.java → controller, non business_critical.
    path_matches_known_cat = any(pat in lower_path for pat, _ in JAVA_CATEGORIES)
    if not path_matches_known_cat:
        basename_no_ext = os.path.splitext(basename)[0].lower()
        for kw in BUSINESS_CRITICAL_NAME_PATTERNS:
            if kw in basename_no_ext or kw in lower_path:
                return "business_critical"

    # Check per contenuto (Python, .py files, ecc.)
    if content and extension not in (".java", ".ts") and _BUSINESS_CRITICAL_CONTENT_RE.search(content):
        return "business_critical"

    # Classificazione per path/nome (Java generico) — DOPO business-critical
    for pattern, cat in JAVA_CATEGORIES:
        if pattern in lower_path:
            return cat

    # Fallback: nome-based BC check per file in path noti (solo se il nome è BC)
    if path_matches_known_cat:
        basename_no_ext = os.path.splitext(basename)[0].lower()
        for kw in BUSINESS_CRITICAL_NAME_PATTERNS:
            if kw in basename_no_ext:
                return "business_critical"

    return "altro"


def _detect_service_and_module(rel_path: str, project_root: str) -> tuple[str, str]:
    """Rileva il microservizio e il sotto-modulo logico di un file.

    Ritorna (service, module) dove:
    - service = microservizio di appartenenza (primo livello, es. "administration-api")
    - module  = sotto-modulo interno (es. "administration-api/core" per Maven multi-modulo,
                oppure uguale a service se non ci sono sotto-moduli)

    Supporta: Maven, Gradle (single/multi-module), Ant, .NET (csproj/sln),
              NPM/Node, strutture esplicite backend/frontend.

    La distinzione è fondamentale per la modalità hybrid:
    - is_hybrid si basa sul numero di SERVICE (microservizi distinti)
    - il chunking si basa sui MODULE (per distribuire il carico token)
    - i documenti generati sono uno per SERVICE, non uno per MODULE
    """
    parts = Path(rel_path).parts

    if not parts:
        return "root", "root"

    first = parts[0].lower()

    # ── 1. Nomi canonici espliciti ────────────────────────────────────────
    SERVICE_ALIASES = {
        "backend": "backend", "server": "backend", "api": "backend", "back-end": "backend",
        "frontend": "frontend", "client": "frontend", "webapp": "frontend",
        "web": "frontend", "front-end": "frontend", "ui": "frontend",
        "infrastructure": "infrastructure", "infra": "infrastructure",
        "deploy": "infrastructure", "devops": "infrastructure",
        "shared": "shared", "common": "shared", "lib": "shared", "libs": "shared",
    }
    if first in SERVICE_ALIASES:
        service = SERVICE_ALIASES[first]
        return service, service

    if len(parts) <= 1:
        # File alla radice del progetto
        return "root", "root"

    first_dir = os.path.join(project_root, parts[0])

    # ── 2. Maven multi-modulo: pom.xml nella prima directory ──────────────
    if os.path.isfile(os.path.join(first_dir, "pom.xml")):
        service = parts[0]
        if len(parts) > 2:
            second_dir = os.path.join(first_dir, parts[1])
            if os.path.isdir(second_dir) and os.path.isfile(os.path.join(second_dir, "pom.xml")):
                # Struttura parent/module/src/... → module = "service/submodule"
                return service, f"{parts[0]}/{parts[1]}"
        return service, service

    # ── 3. Gradle multi-modulo: build.gradle o settings.gradle nella prima dir ──
    if (os.path.isfile(os.path.join(first_dir, "build.gradle"))
            or os.path.isfile(os.path.join(first_dir, "build.gradle.kts"))
            or os.path.isfile(os.path.join(first_dir, "settings.gradle"))
            or os.path.isfile(os.path.join(first_dir, "settings.gradle.kts"))):
        service = parts[0]
        if len(parts) > 2:
            second_dir = os.path.join(first_dir, parts[1])
            if os.path.isdir(second_dir) and (
                os.path.isfile(os.path.join(second_dir, "build.gradle"))
                or os.path.isfile(os.path.join(second_dir, "build.gradle.kts"))
            ):
                # Struttura gradle multi-modulo: service/submodule/src/...
                return service, f"{parts[0]}/{parts[1]}"
        return service, service

    # ── 4. Ant: build.xml nella prima directory ───────────────────────────
    if os.path.isfile(os.path.join(first_dir, "build.xml")):
        service = parts[0]
        # Ant non ha una convenzione standard per sotto-moduli,
        # ma se ci sono sotto-dir con build.xml propri le trattiamo come sotto-moduli
        if len(parts) > 2:
            second_dir = os.path.join(first_dir, parts[1])
            if os.path.isdir(second_dir) and os.path.isfile(os.path.join(second_dir, "build.xml")):
                return service, f"{parts[0]}/{parts[1]}"
        return service, service

    # ── 5. .NET: .csproj nella prima directory ────────────────────────────
    if os.path.isdir(first_dir):
        for fname in os.listdir(first_dir):
            if fname.endswith(".csproj"):
                return parts[0], parts[0]

    # ── 6. NPM/Node: package.json nella prima directory ───────────────────
    # Gestisce sia frontend (Angular, React, Vue) che backend (NestJS, Express)
    if os.path.isfile(os.path.join(first_dir, "package.json")):
        service = parts[0]
        # Controlla se è un monorepo con sotto-pacchetti (es. Nx, Lerna)
        # Struttura: service/packages/subpackage/package.json
        if len(parts) > 3 and parts[1].lower() in ("packages", "apps", "libs", "services"):
            second_dir = os.path.join(first_dir, parts[1], parts[2])
            if os.path.isdir(second_dir) and os.path.isfile(os.path.join(second_dir, "package.json")):
                return service, f"{parts[0]}/{parts[2]}"
        return service, service

    # ── 7. Heuristica basata su estensione (fallback) ─────────────────────
    # A questo punto non abbiamo trovato un build file riconoscibile.
    # Usiamo l'estensione come hint, ma manteniamo parts[0] come service
    # se la struttura è chiaramente multi-directory (progetto multi-servizio).
    ext = os.path.splitext(rel_path)[1]

    # Se la prima directory esiste ed è una directory reale (non un alias),
    # la trattiamo come service name indipendentemente dall'estensione.
    # Questo gestisce microservizi con build system non standard o senza build file.
    if os.path.isdir(first_dir) and len(parts) > 1:
        return parts[0], parts[0]

    # Fallback finale per file alla radice senza struttura riconoscibile
    if ext == ".java":
        return "backend", "backend"
    if ext == ".cs":
        return "backend", "backend"
    if ext in (".ts", ".js") and "src/app" in rel_path.replace("\\", "/"):
        return "frontend", "frontend"

    return "root", "root"


def _detect_module(rel_path: str, project_root: str) -> str:
    """Compatibilità: ritorna solo il module (sotto-modulo).

    Usa _detect_service_and_module internamente.
    """
    _, module = _detect_service_and_module(rel_path, project_root)
    return module


def _truncate_content(content: str, max_chars: int) -> tuple[str, bool]:
    """Tronca contenuto mantenendo inizio e fine."""
    if len(content) <= max_chars:
        return content, False

    keep = max_chars // 2
    marker = f"\n\n... [TRONCATO: {len(content)} caratteri totali, mostrati inizio + fine] ...\n\n"
    return content[:keep] + marker + content[-keep:], True


def scan_project(config: DocGenConfig) -> ScanResult:
    """Scansiona il progetto e ritorna i file classificati.

    Esegue un walk del filesystem, filtra le directory e i file secondo
    la configurazione, legge il contenuto e classifica ogni file.
    """
    result = ScanResult()
    root = os.path.abspath(config.project_path)
    seen_modules: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Filtra directory da ignorare (modifica in-place per os.walk)
        dirnames[:] = [
            d for d in dirnames
            if d not in config.ignore_dirs and not d.startswith(".")
        ]

        for filename in filenames:
            abs_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(abs_path, root)
            ext = os.path.splitext(filename)[1].lower()

            # Controlla se il file deve essere incluso
            if filename not in config.include_filenames and ext not in config.include_extensions:
                continue

            # Controlla dimensione
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                result.error_count += 1
                continue

            if size > config.max_file_bytes:
                result.skipped_count += 1
                continue

            if size == 0:
                continue

            # Leggi contenuto
            content = ""
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except (OSError, PermissionError):
                result.error_count += 1
                continue

            # Classifica prima (serve per troncamento adattivo)
            category = _classify_file(rel_path, ext, content)

            # Tronca se necessario — limite adattivo per categoria
            from .config import TRUNCATION_LIMITS
            trunc_limit = TRUNCATION_LIMITS.get(category, config.max_file_chars)
            content, truncated = _truncate_content(content, trunc_limit)

            priority = PRIORITY_MAP.get(category, "bassa")
            service, module = _detect_service_and_module(rel_path, root)
            seen_modules.add(module)

            scanned = ScannedFile(
                path=rel_path,
                abs_path=abs_path,
                extension=ext,
                category=category,
                priority=priority,
                size_bytes=size,
                content=content,
                module=module,
                service=service,
                truncated=truncated,
            )
            result.files.append(scanned)
            result.total_chars += len(content)

    result.modules = sorted(seen_modules)
    result.services = sorted({f.service for f in result.files if f.service})

    # Ordina per priorità (alta prima) poi per path
    priority_order = {"alta": 0, "media": 1, "bassa": 2}
    result.files.sort(key=lambda f: (priority_order.get(f.priority, 2), f.path))

    return result
