"""Analizzatore statico — estrae endpoint, entità, route, configurazioni via regex."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .scanner import ScanResult, ScannedFile


# ── Dataclass risultati ─────────────────────────────────────────────────────

@dataclass
class RestEndpoint:
    method: str          # GET, POST, PUT, DELETE, PATCH
    path: str            # /api/utenti/{id}
    handler: str         # nome metodo
    file: str            # path relativo del file

@dataclass
class JpaEntity:
    name: str            # Nome classe
    table: str           # Nome tabella
    fields: list[str]    # Campi con tipo
    file: str

@dataclass
class AngularRoute:
    path: str            # path della route
    component: str       # componente associato
    lazy: bool           # se è lazy-loaded
    file: str

@dataclass
class AngularComponent:
    name: str            # Nome classe
    selector: str        # app-utenti
    file: str

@dataclass
class Dependency:
    name: str
    version: str
    scope: str           # "maven", "npm"

@dataclass
class DbInfo:
    url: str = ""
    driver: str = ""
    ddl_auto: str = ""
    port: str = ""

@dataclass
class ProjectAnalysis:
    """Risultato completo dell'analisi statica."""

    endpoints: list[RestEndpoint] = field(default_factory=list)
    entities: list[JpaEntity] = field(default_factory=list)
    routes: list[AngularRoute] = field(default_factory=list)
    components: list[AngularComponent] = field(default_factory=list)
    maven_deps: list[Dependency] = field(default_factory=list)
    npm_deps: list[Dependency] = field(default_factory=list)
    nuget_deps: list[Dependency] = field(default_factory=list)
    generic_deps: list[Dependency] = field(default_factory=list)
    db_info: DbInfo = field(default_factory=DbInfo)

    def summary_text(self) -> str:
        """Produce un riepilogo testuale per l'LLM."""
        lines: list[str] = []

        if self.endpoints:
            lines.append("## Endpoint REST rilevati")
            for ep in self.endpoints:
                lines.append(f"- {ep.method} {ep.path}  →  {ep.handler} ({ep.file})")
            lines.append("")

        if self.entities:
            lines.append("## Entità JPA rilevate")
            for ent in self.entities:
                table_info = f" (tabella: {ent.table})" if ent.table else ""
                lines.append(f"### {ent.name}{table_info}")
                for fld in ent.fields:
                    lines.append(f"  - {fld}")
                lines.append(f"  File: {ent.file}")
            lines.append("")

        if self.routes:
            lines.append("## Route Angular rilevate")
            for r in self.routes:
                lazy = " [LAZY]" if r.lazy else ""
                lines.append(f"- /{r.path} → {r.component}{lazy} ({r.file})")
            lines.append("")

        if self.components:
            lines.append("## Componenti Angular rilevati")
            for c in self.components:
                lines.append(f"- {c.name} (selector: {c.selector}) — {c.file}")
            lines.append("")

        if self.maven_deps:
            lines.append("## Dipendenze Maven principali")
            for d in self.maven_deps:
                lines.append(f"- {d.name}:{d.version}")
            lines.append("")

        if self.npm_deps:
            lines.append("## Dipendenze NPM principali")
            for d in self.npm_deps:
                lines.append(f"- {d.name}@{d.version}")
            lines.append("")

        if self.nuget_deps:
            lines.append("## Dipendenze NuGet principali")
            for d in self.nuget_deps:
                lines.append(f"- {d.name} {d.version}")
            lines.append("")

        if self.generic_deps:
            # Raggruppa per scope
            by_scope: dict[str, list[Dependency]] = {}
            for d in self.generic_deps:
                by_scope.setdefault(d.scope, []).append(d)
            for scope, deps in sorted(by_scope.items()):
                lines.append(f"## Dipendenze {scope.title()} principali")
                for d in deps[:20]:  # Max 20 per sezione
                    ver = f" {d.version}" if d.version else ""
                    lines.append(f"- {d.name}{ver}")
                if len(deps) > 20:
                    lines.append(f"  ... +{len(deps) - 20} altre")
                lines.append("")

        if self.db_info.url:
            lines.append("## Configurazione Database")
            lines.append(f"- URL: {self.db_info.url}")
            if self.db_info.driver:
                lines.append(f"- Driver: {self.db_info.driver}")
            if self.db_info.ddl_auto:
                lines.append(f"- DDL Auto: {self.db_info.ddl_auto}")
            if self.db_info.port:
                lines.append(f"- Server Port: {self.db_info.port}")
            lines.append("")

        return "\n".join(lines) if lines else "Nessuna informazione strutturale rilevata."


# ── Estrattori ───────────────────────────────────────────────────────────────

# Regex per mapping Spring (solo method-level, esclude RequestMapping)
_MAPPING_RE = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping\s*(?:\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\'])?',
    re.IGNORECASE,
)
_CLASS_MAPPING_RE = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']*)["\']',
)
_CLASS_NAME_RE = re.compile(r'public\s+class\s+(\w+)')

# Regex per entità JPA
_ENTITY_RE = re.compile(r'@Entity')
_TABLE_RE = re.compile(r'@Table\s*\(\s*name\s*=\s*["\'](\w+)["\']')
_FIELD_RE = re.compile(
    r'private\s+([\w<>\[\],\s]+?)\s+(\w+)\s*[;=]'
)
_COLUMN_RE = re.compile(r'@Column\s*\(([^)]+)\)')
_ID_RE = re.compile(r'@Id\b')
_GENERATED_RE = re.compile(r'@GeneratedValue')

# Regex per Angular route
_ROUTE_RE = re.compile(
    r"""\{\s*path\s*:\s*['"]([\w/:*-]*)['"]\s*,\s*component\s*:\s*(\w+)""",
)
_LAZY_ROUTE_RE = re.compile(
    r"""path\s*:\s*['"]([\w/:*-]*)['"].*?loadChildren""",
    re.DOTALL,
)

# Regex per Angular component
_COMPONENT_SELECTOR_RE = re.compile(
    r"""selector\s*:\s*['"]([\w-]+)['"]"""
)
_COMPONENT_CLASS_RE = re.compile(
    r"""export\s+class\s+(\w+Component)"""
)

# Regex per POM dependency
_POM_DEP_RE = re.compile(
    r'<dependency>\s*<groupId>(.*?)</groupId>\s*<artifactId>(.*?)</artifactId>'
    r'(?:\s*<version>(.*?)</version>)?',
    re.DOTALL,
)

# Regex per application.yml / .properties
_PROP_URL_RE = re.compile(r'(?:url|jdbc-url)\s*[=:]\s*(.+)')
_PROP_DRIVER_RE = re.compile(r'driver-class-name\s*[=:]\s*(.+)')
_PROP_DDL_RE = re.compile(r'ddl-auto\s*[=:]\s*(.+)')
_PROP_PORT_RE = re.compile(r'server\.port\s*[=:]\s*(\d+)')
_YAML_PORT_RE = re.compile(r'port\s*:\s*(\d+)')


def _extract_endpoints(file: ScannedFile) -> list[RestEndpoint]:
    """Estrae endpoint REST da un file Java."""
    endpoints: list[RestEndpoint] = []
    content = file.content

    # Trova base path dalla classe
    base_path = ""
    class_match = _CLASS_MAPPING_RE.search(content)
    if class_match:
        base_path = class_match.group(1).rstrip("/")

    for match in _MAPPING_RE.finditer(content):
        method_type = match.group(1).upper()
        path = match.group(2) or ""
        if path:
            full_path = f"{base_path}/{path}".replace("//", "/")
        else:
            full_path = base_path or "/"

        # Cerca il nome del metodo handler (prima riga "public" dopo il mapping)
        after = content[match.end():]
        handler_match = re.search(r'public\s+\S+\s+(\w+)\s*\(', after)
        handler = handler_match.group(1) if handler_match else "unknown"

        endpoints.append(RestEndpoint(
            method=method_type,
            path=full_path,
            handler=handler,
            file=file.path,
        ))

    return endpoints


def _extract_entity(file: ScannedFile) -> JpaEntity | None:
    """Estrae entità JPA da un file Java."""
    content = file.content

    if not _ENTITY_RE.search(content):
        return None

    # Nome classe
    class_match = _CLASS_NAME_RE.search(content)
    name = class_match.group(1) if class_match else "Unknown"

    # Nome tabella
    table_match = _TABLE_RE.search(content)
    table = table_match.group(1) if table_match else ""

    # Campi
    fields: list[str] = []
    for field_match in _FIELD_RE.finditer(content):
        field_type = field_match.group(1).strip()
        field_name = field_match.group(2)
        # Cerca annotazioni vicine
        pos = field_match.start()
        context = content[max(0, pos - 200):pos]
        annotations = []
        if _ID_RE.search(context):
            annotations.append("@Id")
        if _GENERATED_RE.search(context):
            annotations.append("@GeneratedValue")
        ann_str = f" {' '.join(annotations)}" if annotations else ""
        fields.append(f"{field_type} {field_name}{ann_str}")

    return JpaEntity(name=name, table=table, fields=fields, file=file.path)


def _extract_routes(file: ScannedFile) -> list[AngularRoute]:
    """Estrae route Angular da un file TypeScript."""
    routes: list[AngularRoute] = []
    content = file.content

    for match in _ROUTE_RE.finditer(content):
        routes.append(AngularRoute(
            path=match.group(1),
            component=match.group(2),
            lazy=False,
            file=file.path,
        ))

    for match in _LAZY_ROUTE_RE.finditer(content):
        routes.append(AngularRoute(
            path=match.group(1),
            component="(lazy-loaded)",
            lazy=True,
            file=file.path,
        ))

    return routes


def _extract_component(file: ScannedFile) -> AngularComponent | None:
    """Estrae componente Angular da un file TypeScript."""
    content = file.content
    selector_match = _COMPONENT_SELECTOR_RE.search(content)
    class_match = _COMPONENT_CLASS_RE.search(content)

    if not selector_match or not class_match:
        return None

    return AngularComponent(
        name=class_match.group(1),
        selector=selector_match.group(1),
        file=file.path,
    )


def _extract_maven_deps(file: ScannedFile) -> list[Dependency]:
    """Estrae dipendenze Maven da pom.xml."""
    deps: list[Dependency] = []
    for match in _POM_DEP_RE.finditer(file.content):
        group_id = match.group(1).strip()
        artifact_id = match.group(2).strip()
        version = match.group(3).strip() if match.group(3) else "inherited"
        deps.append(Dependency(
            name=f"{group_id}:{artifact_id}",
            version=version,
            scope="maven",
        ))
    return deps


def _extract_npm_deps(file: ScannedFile) -> list[Dependency]:
    """Estrae dipendenze NPM da package.json."""
    import json
    deps: list[Dependency] = []
    try:
        pkg = json.loads(file.content)
    except (json.JSONDecodeError, ValueError):
        return deps

    for section in ("dependencies", "devDependencies"):
        for name, version in pkg.get(section, {}).items():
            deps.append(Dependency(name=name, version=version, scope="npm"))
    return deps


def _extract_db_info(file: ScannedFile) -> DbInfo:
    """Estrae info database da file di configurazione."""
    content = file.content
    info = DbInfo()

    url_match = _PROP_URL_RE.search(content)
    if url_match:
        info.url = url_match.group(1).strip()

    driver_match = _PROP_DRIVER_RE.search(content)
    if driver_match:
        info.driver = driver_match.group(1).strip()

    ddl_match = _PROP_DDL_RE.search(content)
    if ddl_match:
        info.ddl_auto = ddl_match.group(1).strip()

    port_match = _PROP_PORT_RE.search(content) or _YAML_PORT_RE.search(content)
    if port_match:
        info.port = port_match.group(1).strip()

    return info


# ── Estrattori C# / ASP.NET Core ────────────────────────────────────────────

# Regex per endpoint ASP.NET Core: [HttpGet("path")], [HttpPost], ecc.
_DOTNET_HTTP_RE = re.compile(
    r'\[(Http(?:Get|Post|Put|Delete|Patch))\s*(?:\(\s*["\']([^"\']*?)["\']\s*\))?\s*\]',
)
# Route a livello controller: [Route("api/[controller]")] o [Route("api/users")]
_DOTNET_ROUTE_RE = re.compile(
    r'\[Route\s*\(\s*["\']([^"\']+)["\']\s*\)\]',
)
# Nome classe C#
_CS_CLASS_RE = re.compile(r'(?:public|internal)\s+class\s+(\w+)')


def _extract_dotnet_endpoints(file: ScannedFile) -> list[RestEndpoint]:
    """Estrae endpoint REST da un controller ASP.NET Core."""
    endpoints: list[RestEndpoint] = []
    content = file.content

    # Trova base route dal controller
    base_path = ""
    route_match = _DOTNET_ROUTE_RE.search(content)
    if route_match:
        base_path = route_match.group(1).rstrip("/")
        # Sostituisci [controller] con il nome del controller
        class_match = _CS_CLASS_RE.search(content)
        if class_match and "[controller]" in base_path.lower():
            ctrl_name = class_match.group(1).replace("Controller", "").lower()
            base_path = re.sub(r'\[controller\]', ctrl_name, base_path, flags=re.IGNORECASE)

    for match in _DOTNET_HTTP_RE.finditer(content):
        method_type = match.group(1).replace("Http", "").upper()
        path = match.group(2) or ""
        if path:
            full_path = f"/{base_path}/{path}".replace("//", "/")
        else:
            full_path = f"/{base_path}" if base_path else "/"

        # Cerca il nome del metodo (public ... NomeMetodo(...) subito dopo l'attributo)
        after = content[match.end():]
        handler_match = re.search(r'(?:public|private)\s+(?:async\s+)?(?:Task<)?(?:IActionResult|ActionResult|[\w<>]+)\>?\s+(\w+)\s*\(', after)
        handler = handler_match.group(1) if handler_match else "unknown"

        endpoints.append(RestEndpoint(
            method=method_type,
            path=full_path,
            handler=handler,
            file=file.path,
        ))

    return endpoints


# Regex per entità EF Core
_CS_TABLE_RE = re.compile(r'\[Table\s*\(\s*["\'](\w+)["\']\s*\)\]')
_CS_KEY_RE = re.compile(r'\[Key\]')
_CS_PROPERTY_RE = re.compile(
    r'public\s+([\w<>\[\]?]+)\s+(\w+)\s*\{\s*get\s*;'
)


def _extract_dotnet_entity(file: ScannedFile) -> JpaEntity | None:
    """Estrae entità EF Core da un file C#."""
    content = file.content

    class_match = _CS_CLASS_RE.search(content)
    if not class_match:
        return None
    name = class_match.group(1)

    # Tabella
    table_match = _CS_TABLE_RE.search(content)
    table = table_match.group(1) if table_match else ""

    # Proprietà
    fields: list[str] = []
    for prop_match in _CS_PROPERTY_RE.finditer(content):
        prop_type = prop_match.group(1).strip()
        prop_name = prop_match.group(2)
        # Cerca [Key] nelle 200 chars prima
        pos = prop_match.start()
        context = content[max(0, pos - 200):pos]
        annotations = []
        if _CS_KEY_RE.search(context):
            annotations.append("[Key]")
        ann_str = f" {' '.join(annotations)}" if annotations else ""
        fields.append(f"{prop_type} {prop_name}{ann_str}")

    if not fields:
        return None

    return JpaEntity(name=name, table=table, fields=fields, file=file.path)


def _extract_dbcontext_entities(file: ScannedFile) -> list[JpaEntity]:
    """Estrae entità referenziate nel DbContext dal pattern DbSet<Entity>."""
    entities: list[JpaEntity] = []
    content = file.content

    # Pattern: public DbSet<NomeEntita> NomeTabella { get; set; }
    dbset_re = re.compile(r'public\s+DbSet<(\w+)>\s+(\w+)\s*\{')
    for match in dbset_re.finditer(content):
        entities.append(JpaEntity(
            name=match.group(1),
            table=match.group(2),
            fields=["(definita nel DbContext)"],
            file=file.path,
        ))

    return entities


# Regex per NuGet PackageReference
_NUGET_REF_RE = re.compile(
    r'<PackageReference\s+Include\s*=\s*["\']([^"\']+)["\']\s+'
    r'Version\s*=\s*["\']([^"\']+)["\']',
)


def _extract_nuget_deps(file: ScannedFile) -> list[Dependency]:
    """Estrae dipendenze NuGet da un file .csproj."""
    deps: list[Dependency] = []
    for match in _NUGET_REF_RE.finditer(file.content):
        deps.append(Dependency(
            name=match.group(1),
            version=match.group(2),
            scope="nuget",
        ))
    return deps


def _extract_db_info_appsettings(file: ScannedFile) -> DbInfo:
    """Estrae info database da appsettings.json (ConnectionStrings)."""
    import json
    info = DbInfo()
    try:
        settings = json.loads(file.content)
    except (json.JSONDecodeError, ValueError):
        return info

    conn_strings = settings.get("ConnectionStrings", {})
    if not conn_strings:
        return info

    # Prendi la prima connection string
    first_conn = next(iter(conn_strings.values()), "")
    if first_conn:
        info.url = first_conn
        # Inferisci driver dal connection string
        lower = first_conn.lower()
        if "server=" in lower or "data source=" in lower:
            info.driver = "SQL Server"
        elif "host=" in lower and "database=" in lower:
            info.driver = "PostgreSQL"
        elif "data source=" in lower and ".db" in lower:
            info.driver = "SQLite"

    # Porta server (Kestrel)
    kestrel = settings.get("Kestrel", {})
    endpoints = kestrel.get("Endpoints", {}).get("Http", {})
    url = endpoints.get("Url", "")
    port_match = re.search(r':(\d+)', url)
    if port_match:
        info.port = port_match.group(1)

    # Fallback: Urls
    urls = settings.get("Urls", "")
    if not info.port and urls:
        port_match = re.search(r':(\d+)', urls)
        if port_match:
            info.port = port_match.group(1)

    return info


# ── Estrattori generici cross-linguaggio ─────────────────────────────────────

# Endpoint Python (FastAPI, Flask, Django REST)
_PYTHON_ROUTE_RE = re.compile(
    r'''@(?:app|router|api_view)\.\s*(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']''',
    re.IGNORECASE,
)
_PYTHON_DECORATOR_RE = re.compile(
    r'''@(?:app\.route|api_view)\s*\(\s*["\']([^"\']+)["\'](?:.*?methods\s*=\s*\[([^\]]+)\])?''',
    re.IGNORECASE | re.DOTALL,
)
_DJANGO_URL_RE = re.compile(
    r'''path\s*\(\s*["\']([^"\']+)["\']''',
)

# Endpoint NestJS / Express
_NESTJS_RE = re.compile(
    r'''@(Get|Post|Put|Delete|Patch)\s*\(\s*(?:["\']([^"\']*)["\'])?\s*\)''',
)
_EXPRESS_RE = re.compile(
    r'''(?:app|router)\.\s*(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']''',
    re.IGNORECASE,
)

# Entità Python (Django models, SQLAlchemy)
_DJANGO_MODEL_RE = re.compile(
    r'''class\s+(\w+)\s*\(\s*(?:models\.Model|admin\.ModelAdmin)''',
)
_SQLALCHEMY_MODEL_RE = re.compile(
    r'''class\s+(\w+)\s*\(\s*(?:Base|db\.Model)''',
)

# Entità TypeORM / Mongoose
_TYPEORM_ENTITY_RE = re.compile(r'@Entity\s*\(')
_MONGOOSE_SCHEMA_RE = re.compile(r'(?:new\s+)?(?:mongoose\.)?Schema\s*\(')
_PRISMA_MODEL_RE = re.compile(r'^model\s+(\w+)\s*\{', re.MULTILINE)

# Dipendenze Python
_REQUIREMENTS_RE = re.compile(r'^([a-zA-Z0-9_-]+)(?:[=<>!~]+(.+))?$', re.MULTILINE)
_PYPROJECT_DEP_RE = re.compile(r'^([a-zA-Z0-9_-]+)(?:[=<>!~]+(.+))?$', re.MULTILINE)

# Dipendenze Go
_GOMOD_RE = re.compile(r'^\t([^\s]+)\s+(v[\d.]+)', re.MULTILINE)

# Dipendenze Rust
_CARGO_RE = re.compile(r'^(\w[\w-]*)\s*=\s*"([^"]+)"', re.MULTILINE)

# Dipendenze Ruby
_GEMFILE_RE = re.compile(r'''gem\s+["\']([^"\']+)["\']\s*(?:,\s*["\']([^"\']+)["\'])?''')

# Dipendenze PHP
_COMPOSER_RE = re.compile(r'''"([^"]+)":\s*"([^"]+)"''')


def _extract_generic_endpoints(file: ScannedFile) -> list[RestEndpoint]:
    """Estrae endpoint REST da file Python/Node/Express/NestJS."""
    endpoints: list[RestEndpoint] = []
    content = file.content
    ext = file.extension

    # Python (FastAPI/Flask @app.get, @router.post)
    if ext == ".py":
        for m in _PYTHON_ROUTE_RE.finditer(content):
            endpoints.append(RestEndpoint(
                method=m.group(1).upper(), path=m.group(2),
                handler="", file=file.path,
            ))
        for m in _PYTHON_DECORATOR_RE.finditer(content):
            methods_str = m.group(2) or "GET"
            for method in re.findall(r'[A-Z]+', methods_str.upper()):
                endpoints.append(RestEndpoint(
                    method=method, path=m.group(1),
                    handler="", file=file.path,
                ))

    # NestJS (@Get, @Post decorators on .ts files)
    if ext == ".ts":
        for m in _NESTJS_RE.finditer(content):
            endpoints.append(RestEndpoint(
                method=m.group(1).upper(), path=m.group(2) or "/",
                handler="", file=file.path,
            ))

    # Express.js (app.get, router.post)
    if ext in (".js", ".ts"):
        for m in _EXPRESS_RE.finditer(content):
            endpoints.append(RestEndpoint(
                method=m.group(1).upper(), path=m.group(2),
                handler="", file=file.path,
            ))

    return endpoints


def _extract_generic_entities(file: ScannedFile) -> list[JpaEntity]:
    """Estrae entità/modelli da file Python/TypeORM/Mongoose/Prisma."""
    entities: list[JpaEntity] = []
    content = file.content
    ext = file.extension

    # Django models
    if ext == ".py":
        for m in _DJANGO_MODEL_RE.finditer(content):
            entities.append(JpaEntity(
                name=m.group(1), table="", fields=["(Django model)"], file=file.path,
            ))
        for m in _SQLALCHEMY_MODEL_RE.finditer(content):
            entities.append(JpaEntity(
                name=m.group(1), table="", fields=["(SQLAlchemy model)"], file=file.path,
            ))

    # Prisma
    if ext == ".prisma":
        for m in _PRISMA_MODEL_RE.finditer(content):
            entities.append(JpaEntity(
                name=m.group(1), table="", fields=["(Prisma model)"], file=file.path,
            ))

    # TypeORM (@Entity decorator in .ts)
    if ext == ".ts" and _TYPEORM_ENTITY_RE.search(content):
        class_match = re.search(r'export\s+class\s+(\w+)', content)
        if class_match:
            entities.append(JpaEntity(
                name=class_match.group(1), table="",
                fields=["(TypeORM entity)"], file=file.path,
            ))

    return entities


def _extract_generic_deps(file: ScannedFile) -> list[Dependency]:
    """Estrae dipendenze da requirements.txt, go.mod, Cargo.toml, Gemfile, composer.json."""
    deps: list[Dependency] = []
    content = file.content
    basename = os.path.basename(file.path).lower()

    # Python (requirements.txt, Pipfile)
    if basename in ("requirements.txt", "requirements-dev.txt", "requirements-prod.txt"):
        for m in _REQUIREMENTS_RE.finditer(content):
            if not m.group(1).startswith("#") and not m.group(1).startswith("-"):
                deps.append(Dependency(
                    name=m.group(1), version=m.group(2) or "", scope="pip",
                ))

    # Go
    if basename == "go.mod":
        for m in _GOMOD_RE.finditer(content):
            deps.append(Dependency(name=m.group(1), version=m.group(2), scope="go"))

    # Rust
    if basename == "cargo.toml":
        # Solo la sezione [dependencies]
        dep_section = re.search(r'\[dependencies\]\s*\n(.*?)(?:\n\[|\Z)', content, re.DOTALL)
        if dep_section:
            for m in _CARGO_RE.finditer(dep_section.group(1)):
                deps.append(Dependency(name=m.group(1), version=m.group(2), scope="cargo"))

    # Ruby
    if basename == "gemfile":
        for m in _GEMFILE_RE.finditer(content):
            deps.append(Dependency(name=m.group(1), version=m.group(2) or "", scope="gem"))

    # PHP
    if basename == "composer.json":
        import json
        try:
            pkg = json.loads(content)
            for section in ("require", "require-dev"):
                for name, version in pkg.get(section, {}).items():
                    if not name.startswith("php"):
                        deps.append(Dependency(name=name, version=version, scope="composer"))
        except (json.JSONDecodeError, ValueError):
            pass

    # Python pyproject.toml (basic extraction)
    if basename == "pyproject.toml":
        dep_section = re.search(r'\[project\]\s*\n.*?dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if dep_section:
            for name in re.findall(r'"([a-zA-Z0-9_-]+)', dep_section.group(1)):
                deps.append(Dependency(name=name, version="", scope="pip"))

    return deps


# ── Estrattori generici cross-linguaggio ─────────────────────────────────────

# Endpoint Python (FastAPI, Flask, Django REST)
_PYTHON_ROUTE_RE = re.compile(
    r'''@(?:app|router|api_view)\.\s*(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']''',
    re.IGNORECASE,
)
_PYTHON_DECORATOR_RE = re.compile(
    r'''@(?:app\.route|api_view)\s*\(\s*["\']([^"\']+)["\'](?:.*?methods\s*=\s*\[([^\]]+)\])?''',
    re.IGNORECASE | re.DOTALL,
)
_DJANGO_URL_RE = re.compile(
    r'''path\s*\(\s*["\']([^"\']+)["\']''',
)

# Endpoint NestJS / Express
_NESTJS_RE = re.compile(
    r'''@(Get|Post|Put|Delete|Patch)\s*\(\s*(?:["\']([^"\']*)["\'])?\s*\)''',
)
_EXPRESS_RE = re.compile(
    r'''(?:app|router)\.\s*(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']''',
    re.IGNORECASE,
)

# Entità Python (Django models, SQLAlchemy)
_DJANGO_MODEL_RE = re.compile(
    r'''class\s+(\w+)\s*\(\s*(?:models\.Model|admin\.ModelAdmin)''',
)
_SQLALCHEMY_MODEL_RE = re.compile(
    r'''class\s+(\w+)\s*\(\s*(?:Base|db\.Model)''',
)

# Entità TypeORM / Mongoose
_TYPEORM_ENTITY_RE = re.compile(r'@Entity\s*\(')
_MONGOOSE_SCHEMA_RE = re.compile(r'(?:new\s+)?(?:mongoose\.)?Schema\s*\(')
_PRISMA_MODEL_RE = re.compile(r'^model\s+(\w+)\s*\{', re.MULTILINE)

# Dipendenze Python
_REQUIREMENTS_RE = re.compile(r'^([a-zA-Z0-9_-]+)(?:[=<>!~]+(.+))?$', re.MULTILINE)
_PYPROJECT_DEP_RE = re.compile(r'^([a-zA-Z0-9_-]+)(?:[=<>!~]+(.+))?$', re.MULTILINE)

# Dipendenze Go
_GOMOD_RE = re.compile(r'^\t([^\s]+)\s+(v[\d.]+)', re.MULTILINE)

# Dipendenze Rust
_CARGO_RE = re.compile(r'^(\w[\w-]*)\s*=\s*"([^"]+)"', re.MULTILINE)

# Dipendenze Ruby
_GEMFILE_RE = re.compile(r'''gem\s+["\']([^"\']+)["\']\s*(?:,\s*["\']([^"\']+)["\'])?''')

# Dipendenze PHP
_COMPOSER_RE = re.compile(r'''"([^"]+)":\s*"([^"]+)"''')


def _extract_generic_endpoints(file: ScannedFile) -> list[RestEndpoint]:
    """Estrae endpoint REST da file Python/Node/Express/NestJS."""
    endpoints: list[RestEndpoint] = []
    content = file.content
    ext = file.extension

    # Python (FastAPI/Flask @app.get, @router.post)
    if ext == ".py":
        for m in _PYTHON_ROUTE_RE.finditer(content):
            endpoints.append(RestEndpoint(
                method=m.group(1).upper(), path=m.group(2),
                handler="", file=file.path,
            ))
        for m in _PYTHON_DECORATOR_RE.finditer(content):
            methods_str = m.group(2) or "GET"
            for method in re.findall(r'[A-Z]+', methods_str.upper()):
                endpoints.append(RestEndpoint(
                    method=method, path=m.group(1),
                    handler="", file=file.path,
                ))

    # NestJS (@Get, @Post decorators on .ts files)
    if ext == ".ts":
        for m in _NESTJS_RE.finditer(content):
            endpoints.append(RestEndpoint(
                method=m.group(1).upper(), path=m.group(2) or "/",
                handler="", file=file.path,
            ))

    # Express.js (app.get, router.post)
    if ext in (".js", ".ts"):
        for m in _EXPRESS_RE.finditer(content):
            endpoints.append(RestEndpoint(
                method=m.group(1).upper(), path=m.group(2),
                handler="", file=file.path,
            ))

    return endpoints


def _extract_generic_entities(file: ScannedFile) -> list[JpaEntity]:
    """Estrae entità/modelli da file Python/TypeORM/Mongoose/Prisma."""
    entities: list[JpaEntity] = []
    content = file.content
    ext = file.extension

    # Django models
    if ext == ".py":
        for m in _DJANGO_MODEL_RE.finditer(content):
            entities.append(JpaEntity(
                name=m.group(1), table="", fields=["(Django model)"], file=file.path,
            ))
        for m in _SQLALCHEMY_MODEL_RE.finditer(content):
            entities.append(JpaEntity(
                name=m.group(1), table="", fields=["(SQLAlchemy model)"], file=file.path,
            ))

    # Prisma
    if ext == ".prisma":
        for m in _PRISMA_MODEL_RE.finditer(content):
            entities.append(JpaEntity(
                name=m.group(1), table="", fields=["(Prisma model)"], file=file.path,
            ))

    # TypeORM (@Entity decorator in .ts)
    if ext == ".ts" and _TYPEORM_ENTITY_RE.search(content):
        class_match = re.search(r'export\s+class\s+(\w+)', content)
        if class_match:
            entities.append(JpaEntity(
                name=class_match.group(1), table="",
                fields=["(TypeORM entity)"], file=file.path,
            ))

    return entities


def _extract_generic_deps(file: ScannedFile) -> list[Dependency]:
    """Estrae dipendenze da requirements.txt, go.mod, Cargo.toml, Gemfile, composer.json."""
    deps: list[Dependency] = []
    content = file.content
    basename = os.path.basename(file.path).lower()

    # Python (requirements.txt, Pipfile)
    if basename in ("requirements.txt", "requirements-dev.txt", "requirements-prod.txt"):
        for m in _REQUIREMENTS_RE.finditer(content):
            if not m.group(1).startswith("#") and not m.group(1).startswith("-"):
                deps.append(Dependency(
                    name=m.group(1), version=m.group(2) or "", scope="pip",
                ))

    # Go
    if basename == "go.mod":
        for m in _GOMOD_RE.finditer(content):
            deps.append(Dependency(name=m.group(1), version=m.group(2), scope="go"))

    # Rust
    if basename == "cargo.toml":
        # Solo la sezione [dependencies]
        dep_section = re.search(r'\[dependencies\]\s*\n(.*?)(?:\n\[|\Z)', content, re.DOTALL)
        if dep_section:
            for m in _CARGO_RE.finditer(dep_section.group(1)):
                deps.append(Dependency(name=m.group(1), version=m.group(2), scope="cargo"))

    # Ruby
    if basename == "gemfile":
        for m in _GEMFILE_RE.finditer(content):
            deps.append(Dependency(name=m.group(1), version=m.group(2) or "", scope="gem"))

    # PHP
    if basename == "composer.json":
        import json
        try:
            pkg = json.loads(content)
            for section in ("require", "require-dev"):
                for name, version in pkg.get(section, {}).items():
                    if not name.startswith("php"):
                        deps.append(Dependency(name=name, version=version, scope="composer"))
        except (json.JSONDecodeError, ValueError):
            pass

    # Python pyproject.toml (basic extraction)
    if basename == "pyproject.toml":
        dep_section = re.search(r'\[project\]\s*\n.*?dependencies\s*=\s*\[(.*?)\]', content, re.DOTALL)
        if dep_section:
            for name in re.findall(r'"([a-zA-Z0-9_-]+)', dep_section.group(1)):
                deps.append(Dependency(name=name, version="", scope="pip"))

    return deps


# ── Funzione principale ─────────────────────────────────────────────────────

def analyze_project(scan_result: ScanResult) -> ProjectAnalysis:
    """Esegue l'analisi statica completa del progetto scansionato."""
    analysis = ProjectAnalysis()

    # Track entità già trovate per nome (evita duplicati tra DbContext e file entity)
    seen_entities: set[str] = set()

    for file in scan_result.files:
        # ── Java / Spring ──────────────────────────────────────────
        # Endpoint REST (Java)
        if file.category == "controller" and file.extension == ".java":
            analysis.endpoints.extend(_extract_endpoints(file))

        # Entità JPA (Java)
        if file.category == "entity" and file.extension == ".java":
            entity = _extract_entity(file)
            if entity:
                analysis.entities.append(entity)
                seen_entities.add(entity.name)

        # ── C# / ASP.NET Core ─────────────────────────────────────
        # Endpoint REST (C#)
        if file.category == "controller" and file.extension == ".cs":
            analysis.endpoints.extend(_extract_dotnet_endpoints(file))

        # Entità EF Core (C# con [Table] o [Key])
        if file.category == "entity" and file.extension == ".cs":
            entity = _extract_dotnet_entity(file)
            if entity and entity.name not in seen_entities:
                analysis.entities.append(entity)
                seen_entities.add(entity.name)

        # DbContext — estrae DbSet<Entity> come entità
        if file.category == "dbcontext" and file.extension == ".cs":
            for entity in _extract_dbcontext_entities(file):
                if entity.name not in seen_entities:
                    analysis.entities.append(entity)
                    seen_entities.add(entity.name)

        # ── Angular ────────────────────────────────────────────────
        # Route Angular
        if file.category in ("routing", "module") and file.extension == ".ts":
            analysis.routes.extend(_extract_routes(file))

        # Componenti Angular
        if file.category == "component" and file.extension == ".ts":
            comp = _extract_component(file)
            if comp:
                analysis.components.append(comp)

        # ── Dipendenze ─────────────────────────────────────────────
        # Maven
        if file.category == "build_config" and file.path.endswith("pom.xml"):
            analysis.maven_deps.extend(_extract_maven_deps(file))

        # NuGet (.csproj)
        if file.category == "build_config" and file.extension == ".csproj":
            analysis.nuget_deps.extend(_extract_nuget_deps(file))

        # NPM
        if file.category == "package_config":
            analysis.npm_deps.extend(_extract_npm_deps(file))

        # ── Estrattori generici cross-linguaggio ───────────────────
        # Endpoint Python/Node/Express/NestJS
        if file.extension in (".py", ".ts", ".js"):
            if file.category not in ("controller", "test"):
                generic_eps = _extract_generic_endpoints(file)
                if generic_eps:
                    analysis.endpoints.extend(generic_eps)

        # Entità Python/TypeORM/Prisma
        if file.extension in (".py", ".ts", ".prisma"):
            if file.category not in ("entity",):
                for entity in _extract_generic_entities(file):
                    if entity.name not in seen_entities:
                        analysis.entities.append(entity)
                        seen_entities.add(entity.name)

        # Dipendenze generiche (requirements.txt, go.mod, Cargo.toml, etc.)
        basename = os.path.basename(file.path).lower()
        if basename in ("requirements.txt", "requirements-dev.txt", "requirements-prod.txt",
                        "go.mod", "cargo.toml", "gemfile", "composer.json", "pyproject.toml"):
            analysis.generic_deps.extend(_extract_generic_deps(file))

        # ── Configurazione DB ──────────────────────────────────────
        # Spring (application.yml/.properties)
        if file.category == "app_config" and file.extension in (".yml", ".yaml", ".properties"):
            db = _extract_db_info(file)
            if db.url:
                analysis.db_info = db

        # ASP.NET (appsettings.json)
        if file.category == "app_config" and "appsettings" in file.path.lower():
            db = _extract_db_info_appsettings(file)
            if db.url:
                analysis.db_info = db

    return analysis
