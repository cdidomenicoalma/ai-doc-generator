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

    def summary_text_for_module(self, module_name: str) -> str:
        """Produce un riepilogo testuale filtrato per un singolo modulo.

        Filtra endpoint, entità, route, componenti per quelli il cui file
        inizia col prefisso del modulo.
        """
        lines: list[str] = []

        mod_endpoints = [ep for ep in self.endpoints if ep.file.startswith(module_name + "/") or ep.file.startswith(module_name + os.sep)]
        if mod_endpoints:
            lines.append("## Endpoint REST rilevati")
            for ep in mod_endpoints:
                lines.append(f"- {ep.method} {ep.path}  →  {ep.handler} ({ep.file})")
            lines.append("")

        mod_entities = [ent for ent in self.entities if ent.file.startswith(module_name + "/") or ent.file.startswith(module_name + os.sep)]
        if mod_entities:
            lines.append("## Entità rilevate")
            for ent in mod_entities:
                table_info = f" (tabella: {ent.table})" if ent.table else ""
                lines.append(f"### {ent.name}{table_info}")
                for fld in ent.fields:
                    lines.append(f"  - {fld}")
                lines.append(f"  File: {ent.file}")
            lines.append("")

        mod_routes = [r for r in self.routes if r.file.startswith(module_name + "/") or r.file.startswith(module_name + os.sep)]
        if mod_routes:
            lines.append("## Route frontend rilevate")
            for r in mod_routes:
                lazy = " [LAZY]" if r.lazy else ""
                lines.append(f"- /{r.path} → {r.component}{lazy} ({r.file})")
            lines.append("")

        mod_components = [c for c in self.components if c.file.startswith(module_name + "/") or c.file.startswith(module_name + os.sep)]
        if mod_components:
            lines.append("## Componenti frontend rilevati")
            for c in mod_components:
                lines.append(f"- {c.name} (selector: {c.selector}) — {c.file}")
            lines.append("")

        # Dipendenze e DB: mostrate solo se il progetto non è multi-modulo o come fallback
        if self.db_info.url:
            lines.append("## Configurazione Database")
            lines.append(f"- URL: {self.db_info.url}")
            if self.db_info.driver:
                lines.append(f"- Driver: {self.db_info.driver}")
            if self.db_info.port:
                lines.append(f"- Server Port: {self.db_info.port}")
            lines.append("")

        # Fallback: se non c'è nulla di specifico, ritorna il summary completo
        if not lines:
            return self.summary_text()

        return "\n".join(lines)


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


# ═══════════════════════════════════════════════════════════════════════════════
# Modalità TESTS — analisi statica estesa
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class MethodSignature:
    """Firma di un metodo pubblico o protetto."""
    class_name: str
    method_name: str
    params: list[str]        # ["String nome", "int eta"]
    return_type: str         # "ResponseEntity<UserDto>"
    annotations: list[str]   # ["@Transactional", "@Override"]
    throws: list[str]        # ["ResourceNotFoundException"]
    visibility: str          # "public" | "protected"
    file: str
    module: str


@dataclass
class ValidationRule:
    """Regola di validazione su campo o parametro."""
    class_name: str
    field_or_param: str      # nome campo o parametro
    annotation: str          # "@NotNull", "@Size(min=1, max=255)"
    file: str
    module: str


@dataclass
class SecurityRule:
    """Vincolo di sicurezza/autorizzazione su classe o metodo."""
    resource: str            # "ClassName.methodName" o "ClassName"
    constraint: str          # "hasRole('ADMIN')", "ROLE_USER, ROLE_ADMIN"
    annotation_type: str     # "PreAuthorize" | "RolesAllowed" | "Secured" | "Authorize" | "UseGuards"
    file: str
    module: str


@dataclass
class EnumDefinition:
    """Definizione di un tipo enumerato."""
    name: str
    values: list[str]
    file: str
    module: str


@dataclass
class ExternalCall:
    """Chiamata verso un sistema o servizio esterno."""
    caller_class: str
    call_type: str           # "RestTemplate" | "WebClient" | "Feign" | "HttpClient" | "axios" | "fetch" | "requests"
    target: str              # URL o nome servizio se rilevabile
    file: str
    module: str


@dataclass
class ExceptionItem:
    """Eccezione lanciata o gestita."""
    exception_type: str
    context: str             # "ClassName.methodName" o "GlobalExceptionHandler"
    is_thrown: bool          # True=throw new, False=catch/@ExceptionHandler
    file: str
    module: str


@dataclass
class TestStaticAnalysis:
    """Analisi statica estesa per la modalità tests."""

    method_signatures: list[MethodSignature] = field(default_factory=list)
    validation_rules: list[ValidationRule] = field(default_factory=list)
    security_rules: list[SecurityRule] = field(default_factory=list)
    enums: list[EnumDefinition] = field(default_factory=list)
    external_calls: list[ExternalCall] = field(default_factory=list)
    exceptions: list[ExceptionItem] = field(default_factory=list)

    def summary_text(self) -> str:
        """Produce il riepilogo testuale per l'LLM (analisi completa)."""
        return self._build_summary(module_filter=None)

    def summary_text_for_module(self, module_name: str) -> str:
        """Produce il riepilogo testuale filtrato per un singolo modulo."""
        return self._build_summary(module_filter=module_name)

    def _build_summary(self, module_filter: str | None) -> str:
        def _match(item_module: str) -> bool:
            if module_filter is None:
                return True
            return (
                item_module == module_filter
                or item_module.startswith(module_filter + "/")
                or item_module.startswith(module_filter + os.sep)
            )

        lines: list[str] = []

        # Firme metodi
        sigs = [s for s in self.method_signatures if _match(s.module)]
        if sigs:
            lines.append("## Firme di metodi — strati critici\n")
            by_class: dict[str, list[MethodSignature]] = {}
            for s in sigs:
                by_class.setdefault(s.class_name, []).append(s)
            for cls, methods in sorted(by_class.items()):
                lines.append(f"### {cls}\n")
                for m in methods:
                    params_str = ", ".join(m.params) if m.params else ""
                    throws_str = f" throws {', '.join(m.throws)}" if m.throws else ""
                    ann_str = f" [{', '.join(m.annotations)}]" if m.annotations else ""
                    lines.append(f"- `{m.visibility} {m.return_type} {m.method_name}({params_str}){throws_str}`{ann_str}")
                lines.append("")

        # Regole di validazione
        validations = [v for v in self.validation_rules if _match(v.module)]
        if validations:
            lines.append("## Regole di validazione\n")
            by_class2: dict[str, list[ValidationRule]] = {}
            for v in validations:
                by_class2.setdefault(v.class_name, []).append(v)
            for cls, rules in sorted(by_class2.items()):
                lines.append(f"### {cls}\n")
                for r in rules:
                    lines.append(f"- `{r.field_or_param}` — {r.annotation}")
                lines.append("")

        # Regole di sicurezza
        security = [s for s in self.security_rules if _match(s.module)]
        if security:
            lines.append("## Regole di sicurezza e autorizzazioni\n")
            for s in security:
                lines.append(f"- `{s.resource}` — @{s.annotation_type}: `{s.constraint}`")
            lines.append("")

        # Enumerazioni
        enums = [e for e in self.enums if _match(e.module)]
        if enums:
            lines.append("## Enumerazioni rilevate\n")
            for e in enums:
                vals = ", ".join(e.values[:20])
                if len(e.values) > 20:
                    vals += f" (+{len(e.values) - 20} altri)"
                lines.append(f"### {e.name}\n")
                lines.append(f"Valori: {vals}\n")
                lines.append(f"File: {e.file}\n")

        # Chiamate esterne
        ext_calls = [c for c in self.external_calls if _match(c.module)]
        if ext_calls:
            lines.append("## Chiamate a sistemi esterni\n")
            for c in ext_calls:
                lines.append(f"- `{c.caller_class}` → {c.call_type}: `{c.target}`  ({c.file})")
            lines.append("")

        # Eccezioni
        thrown = [e for e in self.exceptions if e.is_thrown and _match(e.module)]
        caught = [e for e in self.exceptions if not e.is_thrown and _match(e.module)]
        if thrown:
            lines.append("## Eccezioni lanciate (throw new)\n")
            for e in thrown:
                lines.append(f"- `{e.exception_type}` in `{e.context}` ({e.file})")
            lines.append("")
        if caught:
            lines.append("## Eccezioni gestite (catch / @ExceptionHandler)\n")
            for e in caught:
                lines.append(f"- `{e.exception_type}` in `{e.context}` ({e.file})")
            lines.append("")

        return "\n".join(lines) if lines else ""


# ── Regex per estrattori estesi ─────────────────────────────────────────────

# Java/C# — metodi pubblici/protetti (semplificato per robustezza)
_JAVA_PUBLIC_METHOD_RE = re.compile(
    r'(public|protected)\s+'
    r'(?:static\s+|final\s+|abstract\s+|synchronized\s+|default\s+)*'
    r'([\w<>\[\]?,\s]{1,80}?)\s+'
    r'(\w+)\s*'
    r'\(([^)]{0,400})\)'
    r'(?:\s+throws\s+([\w,\s<>]+?))?'
    r'\s*(?:\{|;)',
    re.MULTILINE,
)

# Annotazioni comuni (Java/Spring/Jakarta)
_ANN_TRANSACTIONAL_RE = re.compile(r'@Transactional\b')
_ANN_OVERRIDE_RE = re.compile(r'@Override\b')
_ANN_DEPRECATED_RE = re.compile(r'@Deprecated\b')
_ANN_ASYNC_RE = re.compile(r'@Async\b')
_ANN_CACHE_RE = re.compile(r'@Cacheable|@CacheEvict|@CachePut')
_ANN_SCHEDULED_RE = re.compile(r'@Scheduled\b')

# Bean Validation (Jakarta/javax)
_BEAN_VALIDATION_RE = re.compile(
    r'@(NotNull|NotBlank|NotEmpty|Size|Min|Max|Email|Pattern|Positive|PositiveOrZero|'
    r'Negative|NegativeOrZero|AssertTrue|AssertFalse|Valid|Validated|Digits|DecimalMin|DecimalMax|Future|Past)'
    r'(\([^)]{0,200}\))?',
)

# C# DataAnnotations
_CS_VALIDATION_RE = re.compile(
    r'\[(Required|StringLength|Range|EmailAddress|MinLength|MaxLength|RegularExpression|'
    r'DataType|Compare|Phone|Url|CreditCard|FileExtensions)'
    r'(?:\([^)]{0,200}\))?\]',
)

# TypeScript class-validator
_TS_VALIDATION_RE = re.compile(
    r'@(IsString|IsEmail|IsNumber|IsInt|IsBoolean|IsArray|IsOptional|IsNotEmpty|'
    r'IsUUID|IsDate|IsEnum|MinLength|MaxLength|Min|Max|Matches|IsDefined|IsObject)'
    r'(?:\([^)]{0,100}\))?',
)

# Spring Security
_PREAUTHORIZE_RE = re.compile(
    r'@PreAuthorize\s*\(\s*["\'](.+?)["\']\s*\)',
    re.DOTALL,
)
_ROLES_ALLOWED_RE = re.compile(
    r'@RolesAllowed\s*\(\s*(?:\{([^}]+)\}|["\']([^"\']+)["\'])\s*\)',
)
_SECURED_RE = re.compile(
    r'@Secured\s*\(\s*(?:\{([^}]+)\}|["\']([^"\']+)["\'])\s*\)',
)
_PERMIT_ALL_RE = re.compile(r'@PermitAll\b')

# C# Authorize
_CSHARP_AUTHORIZE_RE = re.compile(
    r'\[Authorize(?:\(([^)]{0,200})\))?\]',
)

# NestJS guards/roles
_NESTJS_GUARDS_RE = re.compile(r'@UseGuards\s*\(([^)]+)\)')
_NESTJS_ROLES_RE = re.compile(r'@Roles\s*\(([^)]+)\)')

# Enumerazioni Java/C#/TypeScript
_JAVA_ENUM_RE = re.compile(
    r'(?:public\s+)?enum\s+(\w+)\s*(?:implements\s+[\w,\s]+\s*)?\{([^}]{0,2000})\}',
    re.DOTALL,
)
_TS_ENUM_RE = re.compile(
    r'(?:export\s+)?enum\s+(\w+)\s*\{([^}]{0,2000})\}',
    re.DOTALL,
)

# Eccezioni: throw new / catch / @ExceptionHandler
_THROW_NEW_RE = re.compile(
    r'throw\s+new\s+([\w.]+(?:Exception|Error|Fault|Problem))\s*\(',
)
_CATCH_RE = re.compile(
    r'\}\s*catch\s*\(\s*([\w.]+(?:\s*\|\s*[\w.]+)*)\s+\w+\s*\)',
)
_EXCEPTION_HANDLER_RE = re.compile(
    r'@ExceptionHandler\s*\(\s*(?:\{([^}]+)\}|([\w.]+)\.class)\s*\)',
)

# Chiamate HTTP esterne
_REST_TEMPLATE_RE = re.compile(
    r'restTemplate\.(getForObject|postForObject|exchange|put|delete|getForEntity|patchForObject)\s*\(',
    re.IGNORECASE,
)
_WEB_CLIENT_RE = re.compile(
    r'\.webClient\(\)\s*\.(get|post|put|delete|patch)\s*\(\)'
    r'|webClient\.(get|post|put|delete|patch)\s*\(\)',
    re.IGNORECASE,
)
_FEIGN_RE = re.compile(
    r'@FeignClient\s*\(\s*(?:name\s*=\s*)?["\']([^"\']+)["\']',
)
_HTTPCLIENT_CS_RE = re.compile(
    r'(?:_httpClient|httpClient)\.(GetAsync|PostAsync|PutAsync|DeleteAsync|PatchAsync)\s*\(',
    re.IGNORECASE,
)
_AXIOS_RE = re.compile(
    r'(?:this\.)?(?:http|axios|httpClient)\.(get|post|put|delete|patch)\s*\(',
    re.IGNORECASE,
)
_FETCH_RE = re.compile(
    r'\bfetch\s*\(\s*["\']([^"\']+)["\']',
)
_REQUESTS_PY_RE = re.compile(
    r'requests\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _get_module_from_path(file_path: str) -> str:
    """Estrae il nome del modulo dal path del file (prima componente del path)."""
    parts = file_path.replace("\\", "/").split("/")
    return parts[0] if parts else ""


def _extract_class_name_from_context(content: str, method_pos: int) -> str:
    """Cerca il nome della classe più vicino sopra la posizione del metodo."""
    before = content[:method_pos]
    # Cerca l'ultima dichiarazione di classe
    matches = list(re.finditer(
        r'(?:public|internal|protected|private)?\s*(?:abstract\s+|sealed\s+)?'
        r'class\s+(\w+)|interface\s+(\w+)',
        before,
    ))
    if matches:
        last = matches[-1]
        return last.group(1) or last.group(2) or "Unknown"
    return "Unknown"


def _collect_method_annotations(content: str, method_pos: int) -> list[str]:
    """Raccoglie le annotazioni nelle 5 righe precedenti al metodo."""
    before = content[max(0, method_pos - 400):method_pos]
    anns: list[str] = []
    if _ANN_TRANSACTIONAL_RE.search(before):
        anns.append("@Transactional")
    if _ANN_OVERRIDE_RE.search(before):
        anns.append("@Override")
    if _ANN_DEPRECATED_RE.search(before):
        anns.append("@Deprecated")
    if _ANN_ASYNC_RE.search(before):
        anns.append("@Async")
    if _ANN_CACHE_RE.search(before):
        anns.append("@Cacheable/@CacheEvict")
    if _ANN_SCHEDULED_RE.search(before):
        anns.append("@Scheduled")
    # Aggiungi security annotations
    if _PREAUTHORIZE_RE.search(before):
        anns.append("@PreAuthorize")
    if _ROLES_ALLOWED_RE.search(before):
        anns.append("@RolesAllowed")
    return anns


def _extract_method_signatures(file: ScannedFile) -> list[MethodSignature]:
    """Estrae firme di metodi pubblici/protetti da Java, C#, Python, TypeScript."""
    sigs: list[MethodSignature] = []
    content = file.content
    ext = file.extension
    module = _get_module_from_path(file.path)

    # ── Java / C# ──────────────────────────────────────────────────
    if ext in (".java", ".cs"):
        for m in _JAVA_PUBLIC_METHOD_RE.finditer(content):
            visibility = m.group(1)
            return_type = m.group(2).strip()
            method_name = m.group(3)
            raw_params = m.group(4) or ""
            raw_throws = m.group(5) or ""

            # Salta costruttori (return type = class name stesso) e metodi triviali
            if method_name[0].isupper() and return_type.strip() in ("", method_name):
                continue
            # Salta getter/setter banali
            if method_name.startswith(("get", "set", "is")) and len(raw_params.strip()) < 20:
                continue

            params = [p.strip() for p in raw_params.split(",") if p.strip()] if raw_params.strip() else []
            throws = [t.strip() for t in raw_throws.split(",") if t.strip()] if raw_throws.strip() else []
            annotations = _collect_method_annotations(content, m.start())
            class_name = _extract_class_name_from_context(content, m.start())

            sigs.append(MethodSignature(
                class_name=class_name,
                method_name=method_name,
                params=params[:6],  # max 6 params per leggibilità
                return_type=return_type[:60],
                annotations=annotations,
                throws=throws[:4],
                visibility=visibility,
                file=file.path,
                module=module,
            ))

    # ── Python ─────────────────────────────────────────────────────
    if ext == ".py":
        py_method_re = re.compile(
            r'^\s{0,4}def\s+(\w+)\s*\(([^)]{0,300})\)\s*(?:->\s*([\w\[\],|\s"\'\.]+?))?:',
            re.MULTILINE,
        )
        py_class_re = re.compile(r'^class\s+(\w+)', re.MULTILINE)
        classes = list(py_class_re.finditer(content))

        for m in py_method_re.finditer(content):
            method_name = m.group(1)
            if method_name.startswith("_"):
                continue  # skip private
            raw_params = m.group(2) or ""
            return_type = (m.group(3) or "").strip()

            # Determina la classe di appartenenza
            pos = m.start()
            class_name = "module-level"
            for cls in classes:
                if cls.start() < pos:
                    class_name = cls.group(1)

            params = [
                p.strip() for p in raw_params.split(",")
                if p.strip() and p.strip() not in ("self", "cls")
            ]
            sigs.append(MethodSignature(
                class_name=class_name,
                method_name=method_name,
                params=params[:6],
                return_type=return_type[:60],
                annotations=[],
                throws=[],
                visibility="public",
                file=file.path,
                module=module,
            ))

    # ── TypeScript ─────────────────────────────────────────────────
    if ext == ".ts":
        ts_method_re = re.compile(
            r'(public|protected)\s+(?:async\s+)?(\w+)\s*'
            r'(?:<[^>]+>)?\s*\(([^)]{0,300})\)\s*(?::\s*([\w<>\[\]|,\s"\']+?))?'
            r'\s*(?:\{|=>)',
            re.MULTILINE,
        )
        for m in ts_method_re.finditer(content):
            visibility = m.group(1)
            method_name = m.group(2)
            if method_name.startswith(("get", "set")) and len(m.group(3) or "") < 10:
                continue
            raw_params = m.group(3) or ""
            return_type = (m.group(4) or "").strip()
            class_name = _extract_class_name_from_context(content, m.start())
            params = [p.strip() for p in raw_params.split(",") if p.strip()]

            sigs.append(MethodSignature(
                class_name=class_name,
                method_name=method_name,
                params=params[:6],
                return_type=return_type[:60],
                annotations=_collect_method_annotations(content, m.start()),
                throws=[],
                visibility=visibility,
                file=file.path,
                module=module,
            ))

    return sigs


def _extract_validation_rules(file: ScannedFile) -> list[ValidationRule]:
    """Estrae regole di validazione (Bean Validation, DataAnnotations, class-validator)."""
    rules: list[ValidationRule] = []
    content = file.content
    ext = file.extension
    module = _get_module_from_path(file.path)

    if ext in (".java", ".cs"):
        regex = _BEAN_VALIDATION_RE if ext == ".java" else _CS_VALIDATION_RE
        for m in regex.finditer(content):
            ann_text = m.group(0)
            # Cerca il nome del campo nelle 3 righe dopo l'annotazione
            after = content[m.end():m.end() + 300]
            field_match = re.search(
                r'(?:private|public|protected)?\s+[\w<>\[\]?,]+\s+(\w+)\s*[;={]'
                r'|(?:val|var)\s+(\w+)\s*:'
                r'|\bparam\b.+?(\w+)[,)]',
                after,
            )
            field_name = "unknown"
            if field_match:
                field_name = field_match.group(1) or field_match.group(2) or field_match.group(3) or "unknown"
            class_name = _extract_class_name_from_context(content, m.start())
            rules.append(ValidationRule(
                class_name=class_name,
                field_or_param=field_name,
                annotation=ann_text[:80],
                file=file.path,
                module=module,
            ))

    if ext == ".ts":
        for m in _TS_VALIDATION_RE.finditer(content):
            ann_text = m.group(0)
            after = content[m.end():m.end() + 200]
            field_match = re.search(r'(\w+)\s*[?!]?\s*:', after)
            field_name = field_match.group(1) if field_match else "unknown"
            class_name = _extract_class_name_from_context(content, m.start())
            rules.append(ValidationRule(
                class_name=class_name,
                field_or_param=field_name,
                annotation=ann_text[:80],
                file=file.path,
                module=module,
            ))

    return rules


def _extract_security_rules(file: ScannedFile) -> list[SecurityRule]:
    """Estrae regole di sicurezza e autorizzazione."""
    rules: list[SecurityRule] = []
    content = file.content
    ext = file.extension
    module = _get_module_from_path(file.path)

    # Spring Security
    if ext == ".java":
        for m in _PREAUTHORIZE_RE.finditer(content):
            resource = _extract_class_name_from_context(content, m.start())
            # Cerca metodo dopo l'annotazione
            after = content[m.end():m.end() + 200]
            meth_match = re.search(r'(?:public|protected)\s+\S+\s+(\w+)\s*\(', after)
            if meth_match:
                resource = f"{resource}.{meth_match.group(1)}"
            rules.append(SecurityRule(
                resource=resource,
                constraint=m.group(1)[:100],
                annotation_type="PreAuthorize",
                file=file.path,
                module=module,
            ))

        for m in _ROLES_ALLOWED_RE.finditer(content):
            roles_raw = m.group(1) or m.group(2) or ""
            roles = re.findall(r'["\']([^"\']+)["\']', roles_raw) or [roles_raw]
            resource = _extract_class_name_from_context(content, m.start())
            rules.append(SecurityRule(
                resource=resource,
                constraint=", ".join(roles)[:100],
                annotation_type="RolesAllowed",
                file=file.path,
                module=module,
            ))

        for m in _SECURED_RE.finditer(content):
            roles_raw = m.group(1) or m.group(2) or ""
            roles = re.findall(r'["\']([^"\']+)["\']', roles_raw) or [roles_raw]
            resource = _extract_class_name_from_context(content, m.start())
            rules.append(SecurityRule(
                resource=resource,
                constraint=", ".join(roles)[:100],
                annotation_type="Secured",
                file=file.path,
                module=module,
            ))

    # C# Authorize
    if ext == ".cs":
        for m in _CSHARP_AUTHORIZE_RE.finditer(content):
            params_raw = m.group(1) or ""
            resource = _extract_class_name_from_context(content, m.start())
            rules.append(SecurityRule(
                resource=resource,
                constraint=params_raw[:100],
                annotation_type="Authorize",
                file=file.path,
                module=module,
            ))

    # NestJS
    if ext == ".ts":
        for m in _NESTJS_GUARDS_RE.finditer(content):
            resource = _extract_class_name_from_context(content, m.start())
            rules.append(SecurityRule(
                resource=resource,
                constraint=m.group(1)[:100],
                annotation_type="UseGuards",
                file=file.path,
                module=module,
            ))
        for m in _NESTJS_ROLES_RE.finditer(content):
            resource = _extract_class_name_from_context(content, m.start())
            rules.append(SecurityRule(
                resource=resource,
                constraint=m.group(1)[:100],
                annotation_type="Roles",
                file=file.path,
                module=module,
            ))

    return rules


def _extract_enums(file: ScannedFile) -> list[EnumDefinition]:
    """Estrae enumerazioni da file Java, C#, TypeScript."""
    enums: list[EnumDefinition] = []
    content = file.content
    ext = file.extension
    module = _get_module_from_path(file.path)

    regex = _TS_ENUM_RE if ext == ".ts" else _JAVA_ENUM_RE
    if ext not in (".java", ".cs", ".ts"):
        return enums

    for m in regex.finditer(content):
        name = m.group(1)
        body = m.group(2)
        # Estrai i valori (salta assignment, commenti, whitespace)
        raw_values = re.findall(r'\b([A-Z][A-Z0-9_]{1,40})\b', body)
        # Filtra duplicati mantenendo ordine
        seen: set[str] = set()
        values: list[str] = []
        for v in raw_values:
            if v not in seen:
                seen.add(v)
                values.append(v)
        if values:
            enums.append(EnumDefinition(
                name=name,
                values=values,
                file=file.path,
                module=module,
            ))

    # Python enums
    if ext == ".py":
        py_enum_re = re.compile(
            r'class\s+(\w+)\s*\(\s*(?:Enum|IntEnum|StrEnum|Flag|IntFlag)\s*\)\s*:\s*\n'
            r'((?:\s+\w+\s*=.+\n)+)',
        )
        for m in py_enum_re.finditer(content):
            name = m.group(1)
            body = m.group(2)
            values = re.findall(r'(\w+)\s*=', body)
            if values:
                enums.append(EnumDefinition(
                    name=name,
                    values=values,
                    file=file.path,
                    module=module,
                ))

    return enums


def _extract_external_calls(file: ScannedFile) -> list[ExternalCall]:
    """Estrae chiamate verso sistemi o servizi esterni."""
    calls: list[ExternalCall] = []
    content = file.content
    ext = file.extension
    module = _get_module_from_path(file.path)
    class_name = _extract_class_name_from_context(content, len(content))

    # Java/Kotlin — RestTemplate
    if ext == ".java":
        for m in _REST_TEMPLATE_RE.finditer(content):
            calls.append(ExternalCall(
                caller_class=_extract_class_name_from_context(content, m.start()),
                call_type="RestTemplate",
                target=m.group(1),
                file=file.path,
                module=module,
            ))
        for m in _WEB_CLIENT_RE.finditer(content):
            http_method = m.group(1) or m.group(2) or "call"
            calls.append(ExternalCall(
                caller_class=_extract_class_name_from_context(content, m.start()),
                call_type="WebClient",
                target=http_method.upper(),
                file=file.path,
                module=module,
            ))
        for m in _FEIGN_RE.finditer(content):
            calls.append(ExternalCall(
                caller_class=_extract_class_name_from_context(content, m.start()),
                call_type="FeignClient",
                target=m.group(1),
                file=file.path,
                module=module,
            ))

    # C# — HttpClient
    if ext == ".cs":
        for m in _HTTPCLIENT_CS_RE.finditer(content):
            calls.append(ExternalCall(
                caller_class=_extract_class_name_from_context(content, m.start()),
                call_type="HttpClient",
                target=m.group(1).replace("Async", ""),
                file=file.path,
                module=module,
            ))

    # TypeScript/JavaScript — axios, Angular HttpClient, fetch
    if ext in (".ts", ".js"):
        for m in _AXIOS_RE.finditer(content):
            calls.append(ExternalCall(
                caller_class=_extract_class_name_from_context(content, m.start()),
                call_type="HttpClient/axios",
                target=m.group(1).upper(),
                file=file.path,
                module=module,
            ))
        for m in _FETCH_RE.finditer(content):
            calls.append(ExternalCall(
                caller_class=_extract_class_name_from_context(content, m.start()),
                call_type="fetch",
                target=m.group(1)[:60],
                file=file.path,
                module=module,
            ))

    # Python — requests
    if ext == ".py":
        for m in _REQUESTS_PY_RE.finditer(content):
            calls.append(ExternalCall(
                caller_class=_extract_class_name_from_context(content, m.start()),
                call_type="requests",
                target=f"{m.group(1).upper()} {m.group(2)[:60]}",
                file=file.path,
                module=module,
            ))

    return calls


def _extract_exceptions(file: ScannedFile) -> list[ExceptionItem]:
    """Estrae eccezioni lanciate, catturate e gestite."""
    items: list[ExceptionItem] = []
    content = file.content
    module = _get_module_from_path(file.path)

    # throw new XxxException
    for m in _THROW_NEW_RE.finditer(content):
        class_name = _extract_class_name_from_context(content, m.start())
        items.append(ExceptionItem(
            exception_type=m.group(1),
            context=class_name,
            is_thrown=True,
            file=file.path,
            module=module,
        ))

    # catch (XxxException | YyyException e)
    for m in _CATCH_RE.finditer(content):
        exc_types_raw = m.group(1)
        for exc_type in re.split(r'\s*\|\s*', exc_types_raw):
            exc_type = exc_type.strip()
            if exc_type and exc_type not in ("Exception", "Throwable", "Error", "e", "ex"):
                class_name = _extract_class_name_from_context(content, m.start())
                items.append(ExceptionItem(
                    exception_type=exc_type,
                    context=class_name,
                    is_thrown=False,
                    file=file.path,
                    module=module,
                ))

    # @ExceptionHandler
    for m in _EXCEPTION_HANDLER_RE.finditer(content):
        exc_raw = m.group(1) or m.group(2) or ""
        for exc in re.findall(r'(\w+)(?:\.class)?', exc_raw):
            if exc:
                class_name = _extract_class_name_from_context(content, m.start())
                items.append(ExceptionItem(
                    exception_type=exc,
                    context=f"{class_name} (@ExceptionHandler)",
                    is_thrown=False,
                    file=file.path,
                    module=module,
                ))

    return items


# Categorie rilevanti per l'analisi test
_TEST_RELEVANT_CATEGORIES = {
    "controller", "service", "business_critical", "entity", "repository",
    "dto", "dbcontext", "angular_service",
}
_TEST_RELEVANT_EXTENSIONS = {".java", ".cs", ".ts", ".js", ".py"}


def analyze_project_for_tests(scan_result: ScanResult) -> TestStaticAnalysis:
    """Esegue l'analisi statica estesa per la modalità tests.

    Opera sui file nei layer rilevanti (controller, service, business_critical,
    entity, repository, dto) e su tutti i file con estensioni rilevanti.
    """
    result = TestStaticAnalysis()

    # De-duplicazione eccezioni e chiamate esterne per evitare rumore
    seen_sigs: set[str] = set()
    seen_exceptions: set[str] = set()
    seen_calls: set[str] = set()

    for file in scan_result.files:
        if file.extension not in _TEST_RELEVANT_EXTENSIONS:
            continue

        is_relevant_category = file.category in _TEST_RELEVANT_CATEGORIES

        # Firme metodi — solo su layer rilevanti
        if is_relevant_category:
            for sig in _extract_method_signatures(file):
                key = f"{sig.class_name}.{sig.method_name}"
                if key not in seen_sigs:
                    seen_sigs.add(key)
                    result.method_signatures.append(sig)

        # Validazioni — su entity, dto, service, controller
        if file.category in ("entity", "dto", "service", "controller", "business_critical"):
            result.validation_rules.extend(_extract_validation_rules(file))

        # Sicurezza — su tutti i file rilevanti
        if is_relevant_category:
            result.security_rules.extend(_extract_security_rules(file))

        # Enumerazioni — su tutti i file rilevanti
        if is_relevant_category:
            result.enums.extend(_extract_enums(file))

        # Chiamate esterne — su service, business_critical, angular_service
        if file.category in ("service", "business_critical", "angular_service"):
            for call in _extract_external_calls(file):
                key = f"{call.caller_class}:{call.call_type}:{call.target}"
                if key not in seen_calls:
                    seen_calls.add(key)
                    result.external_calls.append(call)

        # Eccezioni — su tutti i layer rilevanti
        if is_relevant_category:
            for exc in _extract_exceptions(file):
                key = f"{exc.exception_type}:{exc.context}:{exc.is_thrown}"
                if key not in seen_exceptions:
                    seen_exceptions.add(key)
                    result.exceptions.append(exc)

    return result

