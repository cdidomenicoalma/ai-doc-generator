"""Test suite per DocGen — verifica tutti i moduli."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

# Percorso progetto di test
PROJECT_ROOT = Path(__file__).parent.parent
TEST_PROJECT = PROJECT_ROOT / "test-project"

# Import moduli
from docgen.config import DocGenConfig, CHARS_PER_TOKEN, LARGE_PROJECT_MIN_MODULES, LARGE_PROJECT_MIN_CHUNKS
from docgen.scanner import scan_project, ScanResult, ScannedFile, _classify_file, _detect_module, _truncate_content
from docgen.analyzer import (
    analyze_project, ProjectAnalysis, _extract_endpoints, _extract_entity,
    _extract_routes, _extract_component, _extract_maven_deps, _extract_npm_deps,
    _extract_db_info,
    _extract_dotnet_endpoints, _extract_dotnet_entity, _extract_dbcontext_entities,
    _extract_nuget_deps, _extract_db_info_appsettings,
    _extract_generic_endpoints, _extract_generic_entities, _extract_generic_deps,
)
from docgen.chunker import create_chunks, ChunkPlan, Chunk
from docgen.renderer import markdown_to_docx, _parse_table, _add_inline_formatting, render_documents_hybrid


# ═══════════════════════════════════════════════════════════════════════════════
# Test Config
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfig(unittest.TestCase):

    def test_default_values(self):
        config = DocGenConfig()
        self.assertEqual(config.chunk_budget, 120_000)
        self.assertEqual(config.max_file_chars, 40_000)
        self.assertEqual(config.max_file_bytes, 500_000)
        self.assertFalse(config.dry_run)
        self.assertEqual(config.output_format, "all")

    def test_chars_to_tokens(self):
        config = DocGenConfig()
        self.assertEqual(config.chars_to_tokens(3500), 1000)
        self.assertEqual(config.chars_to_tokens(0), 0)

    def test_tokens_to_chars(self):
        config = DocGenConfig()
        self.assertEqual(config.tokens_to_chars(1000), 3500)

    def test_estimate_cost(self):
        config = DocGenConfig()
        cost = config.estimate_cost(1_000_000, 1_000_000)
        # $3/M input + $15/M output = $18
        self.assertAlmostEqual(cost, 18.0, places=2)

    def test_estimate_cost_zero(self):
        config = DocGenConfig()
        self.assertEqual(config.estimate_cost(0, 0), 0.0)

    def test_ignore_dirs_are_set(self):
        config = DocGenConfig()
        self.assertIn(".git", config.ignore_dirs)
        self.assertIn("node_modules", config.ignore_dirs)
        self.assertIn("target", config.ignore_dirs)

    def test_include_extensions(self):
        config = DocGenConfig()
        self.assertIn(".java", config.include_extensions)
        self.assertIn(".ts", config.include_extensions)
        self.assertIn(".py", config.include_extensions)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Scanner
# ═══════════════════════════════════════════════════════════════════════════════

class TestClassifyFile(unittest.TestCase):

    def test_java_controller_by_annotation(self):
        content = '@RestController\npublic class UserController {}'
        self.assertEqual(_classify_file("src/UserController.java", ".java", content), "controller")

    def test_java_service_by_annotation(self):
        content = '@Service\npublic class UserService {}'
        self.assertEqual(_classify_file("src/UserService.java", ".java", content), "service")

    def test_java_entity_by_annotation(self):
        content = '@Entity\npublic class User {}'
        self.assertEqual(_classify_file("src/User.java", ".java", content), "entity")

    def test_java_repository_by_annotation(self):
        content = '@Repository\npublic interface UserRepo {}'
        self.assertEqual(_classify_file("src/UserRepo.java", ".java", content), "repository")

    def test_java_config_by_annotation(self):
        content = '@Configuration\npublic class AppConfig {}'
        self.assertEqual(_classify_file("src/AppConfig.java", ".java", content), "config")

    def test_java_controller_by_path(self):
        cat = _classify_file("src/main/controller/FooHandler.java", ".java", "public class FooHandler {}")
        self.assertEqual(cat, "controller")

    def test_angular_component(self):
        cat = _classify_file("src/app/users/users.component.ts", ".ts", "")
        self.assertEqual(cat, "component")

    def test_angular_service(self):
        cat = _classify_file("src/app/users/users.service.ts", ".ts", "")
        self.assertEqual(cat, "angular_service")

    def test_angular_routing_module(self):
        cat = _classify_file("src/app/app-routing.module.ts", ".ts", "")
        self.assertEqual(cat, "routing")

    def test_angular_module(self):
        cat = _classify_file("src/app/app.module.ts", ".ts", "")
        self.assertEqual(cat, "module")

    def test_pom_xml(self):
        cat = _classify_file("backend/pom.xml", ".xml", "")
        self.assertEqual(cat, "build_config")

    def test_application_yml(self):
        cat = _classify_file("src/main/resources/application.yml", ".yml", "")
        self.assertEqual(cat, "app_config")

    def test_package_json(self):
        cat = _classify_file("frontend/package.json", ".json", "")
        self.assertEqual(cat, "package_config")

    def test_dockerfile(self):
        cat = _classify_file("Dockerfile", "", "")
        self.assertEqual(cat, "infrastructure")

    def test_unknown_file(self):
        cat = _classify_file("src/utils/Random.java", ".java", "public class Random {}")
        # "utils" in path → util
        self.assertEqual(cat, "util")

    def test_truly_unknown(self):
        cat = _classify_file("src/Foo.java", ".java", "public class Foo {}")
        self.assertEqual(cat, "altro")


class TestDetectModule(unittest.TestCase):

    def test_backend_dir(self):
        self.assertEqual(_detect_module("backend/src/Main.java", "/tmp"), "backend")

    def test_frontend_dir(self):
        self.assertEqual(_detect_module("frontend/src/app/app.ts", "/tmp"), "frontend")

    def test_infrastructure_dir(self):
        self.assertEqual(_detect_module("infrastructure/docker/Dockerfile", "/tmp"), "infrastructure")

    def test_java_heuristic(self):
        self.assertEqual(_detect_module("src/main/java/Foo.java", "/tmp"), "backend")

    def test_angular_heuristic(self):
        self.assertEqual(_detect_module("src/app/component.ts", "/tmp"), "frontend")

    def test_root_fallback(self):
        self.assertEqual(_detect_module("README.md", "/tmp"), "root")


class TestTruncateContent(unittest.TestCase):

    def test_no_truncation_needed(self):
        text = "short text"
        result, truncated = _truncate_content(text, 1000)
        self.assertEqual(result, text)
        self.assertFalse(truncated)

    def test_truncation_occurs(self):
        text = "A" * 20000
        result, truncated = _truncate_content(text, 1000)
        self.assertTrue(truncated)
        self.assertLessEqual(len(result), 20000)
        self.assertIn("TRONCATO", result)

    def test_truncation_preserves_start_end(self):
        text = "START" + "X" * 20000 + "END"
        result, truncated = _truncate_content(text, 2000)
        self.assertTrue(truncated)
        self.assertTrue(result.startswith("START"))
        self.assertTrue(result.endswith("END"))


class TestScanProject(unittest.TestCase):

    def test_scan_test_project(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        result = scan_project(config)
        self.assertGreater(result.total_files, 0)
        self.assertGreater(result.total_chars, 0)
        self.assertEqual(result.error_count, 0)

    def test_scan_finds_all_categories(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        result = scan_project(config)
        categories = {f.category for f in result.files}
        self.assertIn("controller", categories)
        self.assertIn("entity", categories)
        self.assertIn("service", categories)
        self.assertIn("component", categories)

    def test_scan_detects_modules(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        result = scan_project(config)
        self.assertIn("backend", result.modules)
        self.assertIn("frontend", result.modules)

    def test_scan_respects_priority_order(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        result = scan_project(config)
        # I primi file dovrebbero essere alta priorità
        if result.files:
            first = result.files[0]
            self.assertIn(first.priority, ("alta", "media"))

    def test_scan_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DocGenConfig(project_path=tmpdir)
            result = scan_project(config)
            self.assertEqual(result.total_files, 0)

    def test_scan_skips_large_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crea file grande (>500KB)
            big_file = Path(tmpdir) / "huge.java"
            big_file.write_text("x" * 600_000)
            config = DocGenConfig(project_path=tmpdir)
            result = scan_project(config)
            self.assertEqual(result.skipped_count, 1)
            self.assertEqual(result.total_files, 0)

    def test_scan_ignores_git_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()
            (git_dir / "config.yml").write_text("git config")
            (Path(tmpdir) / "Main.java").write_text("public class Main {}")
            config = DocGenConfig(project_path=tmpdir)
            result = scan_project(config)
            paths = [f.path for f in result.files]
            self.assertNotIn(".git/config.yml", paths)

    def test_scan_truncates_long_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            long_file = Path(tmpdir) / "Long.java"
            long_file.write_text("A" * 50_000)  # > 40K default
            config = DocGenConfig(project_path=tmpdir)
            result = scan_project(config)
            self.assertEqual(result.total_files, 1)
            self.assertTrue(result.files[0].truncated)

    def test_scan_result_methods(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        result = scan_project(config)
        by_cat = result.files_by_category()
        self.assertIsInstance(by_cat, dict)
        by_mod = result.files_by_module()
        self.assertIsInstance(by_mod, dict)
        top_ext = result.top_extensions(5)
        self.assertIsInstance(top_ext, list)
        self.assertLessEqual(len(top_ext), 5)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Analyzer
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractEndpoints(unittest.TestCase):

    def _make_file(self, content, path="Controller.java"):
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=".java",
            category="controller", priority="alta", size_bytes=len(content),
            content=content,
        )

    def test_get_mapping(self):
        content = '''
@RestController
@RequestMapping("/api/users")
public class UserController {
    @GetMapping("/{id}")
    public User getById(@PathVariable Long id) { return null; }
}
'''
        eps = _extract_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].method, "GET")
        self.assertEqual(eps[0].path, "/api/users/{id}")
        self.assertEqual(eps[0].handler, "getById")

    def test_post_mapping(self):
        content = '''
@RestController
@RequestMapping("/api/users")
public class UserController {
    @PostMapping("")
    public User create(@RequestBody User user) { return null; }
}
'''
        eps = _extract_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].method, "POST")
        self.assertEqual(eps[0].path, "/api/users")

    def test_delete_mapping(self):
        content = '''
@RestController
@RequestMapping("/api/users")
public class UserController {
    @DeleteMapping("/{id}")
    public void delete(@PathVariable Long id) {}
}
'''
        eps = _extract_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].method, "DELETE")

    def test_multiple_endpoints(self):
        content = '''
@RestController
@RequestMapping("/api/items")
public class ItemController {
    @GetMapping("")
    public List<Item> getAll() { return null; }
    @GetMapping("/{id}")
    public Item getById(@PathVariable Long id) { return null; }
    @PostMapping("")
    public Item create(@RequestBody Item item) { return null; }
    @PutMapping("/{id}")
    public Item update(@PathVariable Long id, @RequestBody Item item) { return null; }
}
'''
        eps = _extract_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 4)
        methods = {ep.method for ep in eps}
        self.assertEqual(methods, {"GET", "POST", "PUT"})

    def test_no_class_mapping(self):
        content = '''
@RestController
public class SimpleController {
    @GetMapping("/health")
    public String health() { return "ok"; }
}
'''
        eps = _extract_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].path, "/health")

    def test_no_endpoints(self):
        content = 'public class PlainClass { }'
        eps = _extract_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 0)


class TestExtractEntity(unittest.TestCase):

    def _make_file(self, content, path="Entity.java"):
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=".java",
            category="entity", priority="alta", size_bytes=len(content),
            content=content,
        )

    def test_basic_entity(self):
        content = '''
@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private String name;
    private String email;
}
'''
        entity = _extract_entity(self._make_file(content))
        self.assertIsNotNone(entity)
        self.assertEqual(entity.name, "User")
        self.assertEqual(entity.table, "users")
        self.assertGreaterEqual(len(entity.fields), 2)

    def test_entity_without_table_annotation(self):
        content = '''
@Entity
public class Product {
    @Id
    private Long id;
    private String title;
}
'''
        entity = _extract_entity(self._make_file(content))
        self.assertIsNotNone(entity)
        self.assertEqual(entity.name, "Product")
        self.assertEqual(entity.table, "")

    def test_no_entity(self):
        content = 'public class NotAnEntity { private String x; }'
        entity = _extract_entity(self._make_file(content))
        self.assertIsNone(entity)


class TestExtractRoutes(unittest.TestCase):

    def _make_file(self, content, path="routing.module.ts"):
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=".ts",
            category="routing", priority="alta", size_bytes=len(content),
            content=content,
        )

    def test_eager_routes(self):
        content = """
const routes: Routes = [
  { path: 'home', component: HomeComponent },
  { path: 'about', component: AboutComponent },
];
"""
        routes = _extract_routes(self._make_file(content))
        self.assertEqual(len(routes), 2)
        self.assertFalse(routes[0].lazy)
        self.assertEqual(routes[0].component, "HomeComponent")

    def test_lazy_route(self):
        content = """
const routes: Routes = [
  { path: 'admin', loadChildren: () => import('./admin/admin.module').then(m => m.AdminModule) },
];
"""
        routes = _extract_routes(self._make_file(content))
        self.assertGreaterEqual(len(routes), 1)
        lazy_routes = [r for r in routes if r.lazy]
        self.assertGreaterEqual(len(lazy_routes), 1)

    def test_no_routes(self):
        content = "const x = 42;"
        routes = _extract_routes(self._make_file(content))
        self.assertEqual(len(routes), 0)


class TestExtractComponent(unittest.TestCase):

    def _make_file(self, content, path="test.component.ts"):
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=".ts",
            category="component", priority="media", size_bytes=len(content),
            content=content,
        )

    def test_basic_component(self):
        content = """
@Component({
  selector: 'app-users',
  templateUrl: './users.component.html'
})
export class UsersComponent implements OnInit { }
"""
        comp = _extract_component(self._make_file(content))
        self.assertIsNotNone(comp)
        self.assertEqual(comp.name, "UsersComponent")
        self.assertEqual(comp.selector, "app-users")

    def test_no_component(self):
        content = "export class SomeService { }"
        comp = _extract_component(self._make_file(content))
        self.assertIsNone(comp)


class TestExtractMavenDeps(unittest.TestCase):

    def _make_file(self, content):
        return ScannedFile(
            path="pom.xml", abs_path="/tmp/pom.xml", extension=".xml",
            category="build_config", priority="alta", size_bytes=len(content),
            content=content,
        )

    def test_dependencies(self):
        content = '''
<project>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.1</version>
        </dependency>
    </dependencies>
</project>
'''
        deps = _extract_maven_deps(self._make_file(content))
        self.assertEqual(len(deps), 2)
        self.assertEqual(deps[0].name, "org.springframework.boot:spring-boot-starter-web")
        self.assertEqual(deps[0].version, "inherited")
        self.assertEqual(deps[1].version, "42.7.1")

    def test_empty_pom(self):
        deps = _extract_maven_deps(self._make_file("<project></project>"))
        self.assertEqual(len(deps), 0)


class TestExtractNpmDeps(unittest.TestCase):

    def _make_file(self, content):
        return ScannedFile(
            path="package.json", abs_path="/tmp/package.json", extension=".json",
            category="package_config", priority="alta", size_bytes=len(content),
            content=content,
        )

    def test_dependencies(self):
        pkg = {"dependencies": {"@angular/core": "^17.0.0", "rxjs": "~7.8.0"}}
        deps = _extract_npm_deps(self._make_file(json.dumps(pkg)))
        self.assertEqual(len(deps), 2)

    def test_dev_dependencies(self):
        pkg = {"devDependencies": {"typescript": "~5.2.0"}}
        deps = _extract_npm_deps(self._make_file(json.dumps(pkg)))
        self.assertEqual(len(deps), 1)

    def test_invalid_json(self):
        deps = _extract_npm_deps(self._make_file("not json"))
        self.assertEqual(len(deps), 0)

    def test_empty_package(self):
        deps = _extract_npm_deps(self._make_file("{}"))
        self.assertEqual(len(deps), 0)


class TestExtractDbInfo(unittest.TestCase):

    def _make_file(self, content):
        return ScannedFile(
            path="application.yml", abs_path="/tmp/application.yml", extension=".yml",
            category="app_config", priority="alta", size_bytes=len(content),
            content=content,
        )

    def test_yaml_config(self):
        content = """
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/mydb
    driver-class-name: org.postgresql.Driver
  jpa:
    hibernate:
      ddl-auto: update
server:
  port: 8080
"""
        info = _extract_db_info(self._make_file(content))
        self.assertEqual(info.url, "jdbc:postgresql://localhost:5432/mydb")
        self.assertEqual(info.driver, "org.postgresql.Driver")
        self.assertEqual(info.ddl_auto, "update")
        self.assertEqual(info.port, "8080")

    def test_properties_config(self):
        content = """
spring.datasource.url=jdbc:mysql://localhost:3306/db
spring.datasource.driver-class-name=com.mysql.cj.jdbc.Driver
spring.jpa.hibernate.ddl-auto=create-drop
server.port=9090
"""
        info = _extract_db_info(self._make_file(content))
        self.assertIn("mysql", info.url)
        self.assertEqual(info.port, "9090")

    def test_no_db_info(self):
        info = _extract_db_info(self._make_file("logging.level.root: INFO"))
        self.assertEqual(info.url, "")


class TestAnalyzeProject(unittest.TestCase):

    def test_full_analysis_on_test_project(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        from docgen.scanner import scan_project
        scan_result = scan_project(config)
        analysis = analyze_project(scan_result)

        self.assertIsInstance(analysis, ProjectAnalysis)
        self.assertGreater(len(analysis.endpoints), 0)
        self.assertGreater(len(analysis.entities), 0)
        self.assertGreater(len(analysis.routes), 0)
        self.assertGreater(len(analysis.components), 0)
        self.assertGreater(len(analysis.maven_deps), 0)
        self.assertGreater(len(analysis.npm_deps), 0)
        self.assertTrue(analysis.db_info.url)

    def test_summary_text_not_empty(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        from docgen.scanner import scan_project
        scan_result = scan_project(config)
        analysis = analyze_project(scan_result)
        summary = analysis.summary_text()
        self.assertIn("Endpoint REST", summary)
        self.assertIn("Entità JPA", summary)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Business Critical Classification
# ═══════════════════════════════════════════════════════════════════════════════

class TestBusinessCriticalClassification(unittest.TestCase):
    """Test per la classificazione business_critical."""

    def test_event_handler_by_name(self):
        cat = _classify_file("src/OrderEventHandler.java", ".java", "public class OrderEventHandler {}")
        self.assertEqual(cat, "business_critical")

    def test_exception_handler_by_name(self):
        cat = _classify_file("src/GlobalExceptionHandler.java", ".java", "public class GlobalExceptionHandler {}")
        self.assertEqual(cat, "business_critical")

    def test_validator_by_name(self):
        cat = _classify_file("src/OrderValidator.java", ".java", "public class OrderValidator {}")
        self.assertEqual(cat, "business_critical")

    def test_interceptor_by_name(self):
        cat = _classify_file("src/AuthInterceptor.java", ".java", "public class AuthInterceptor {}")
        self.assertEqual(cat, "business_critical")

    def test_aspect_by_content(self):
        content = '@Aspect\npublic class LoggingAspect {}'
        cat = _classify_file("src/LoggingAspect.java", ".java", content)
        self.assertEqual(cat, "business_critical")

    def test_security_config_by_content(self):
        content = 'public class SecurityConfig {\n  SecurityFilterChain filterChain(HttpSecurity http) {}\n}'
        cat = _classify_file("src/SecurityConfig.java", ".java", content)
        self.assertEqual(cat, "business_critical")

    def test_controller_advice_by_content(self):
        content = '@ControllerAdvice\npublic class ErrorHandler {}'
        cat = _classify_file("src/ErrorHandler.java", ".java", content)
        self.assertEqual(cat, "business_critical")

    def test_rabbit_listener_by_content(self):
        content = '@Component\npublic class OrderConsumer {\n  @RabbitListener(queues = "orders")\n  void handle() {}\n}'
        cat = _classify_file("src/OrderConsumer.java", ".java", content)
        self.assertEqual(cat, "business_critical")

    def test_aspect_annotation_by_content(self):
        content = '@Aspect\n@Component\npublic class AuditAspect {}'
        cat = _classify_file("src/AuditAspect.java", ".java", content)
        self.assertEqual(cat, "business_critical")

    def test_python_signal_receiver_by_content(self):
        content = 'from django.dispatch import receiver\nfrom django.db.models.signals import post_save\n\n@receiver(post_save, sender=Order)\ndef on_order_saved(sender, **kwargs):\n    pass'
        cat = _classify_file("src/signals.py", ".py", content)
        self.assertEqual(cat, "business_critical")

    def test_nestjs_interceptor_by_content(self):
        content = 'import { UseInterceptors } from "@nestjs/common";\n@UseInterceptors(LoggingInterceptor)\nexport class AppController {}'
        cat = _classify_file("src/app.controller.ts", ".ts", content)
        self.assertEqual(cat, "business_critical")

    def test_business_critical_priority(self):
        from docgen.scanner import PRIORITY_MAP
        self.assertEqual(PRIORITY_MAP.get("business_critical"), "alta")

    def test_regular_service_not_business_critical(self):
        content = '@Service\npublic class UserService {}'
        cat = _classify_file("src/UserService.java", ".java", content)
        self.assertEqual(cat, "service")

    def test_regular_controller_not_business_critical(self):
        content = '@RestController\npublic class UserController {}'
        cat = _classify_file("src/UserController.java", ".java", content)
        self.assertEqual(cat, "controller")


# ═══════════════════════════════════════════════════════════════════════════════
# Test Generic Cross-Language Extractors
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenericEndpoints(unittest.TestCase):
    """Test estrazione endpoint cross-linguaggio."""

    def _make_file(self, content, path="routes.py", ext=".py"):
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=ext,
            category="altro", priority="media", size_bytes=len(content),
            content=content,
        )

    def test_fastapi_get(self):
        content = '@app.get("/api/users")\nasync def get_users():\n    pass'
        eps = _extract_generic_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].method, "GET")
        self.assertEqual(eps[0].path, "/api/users")

    def test_fastapi_router_post(self):
        content = '@router.post("/items")\nasync def create_item():\n    pass'
        eps = _extract_generic_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].method, "POST")

    def test_express_route(self):
        content = 'app.get("/api/users", async (req, res) => {});'
        eps = _extract_generic_endpoints(self._make_file(content, "routes.js", ".js"))
        self.assertEqual(len(eps), 1)
        self.assertEqual(eps[0].method, "GET")
        self.assertEqual(eps[0].path, "/api/users")

    def test_nestjs_controller(self):
        content = '''
@Controller("users")
export class UsersController {
    @Get("/list")
    findAll() {}
    @Post()
    create() {}
}
'''
        eps = _extract_generic_endpoints(self._make_file(content, "users.controller.ts", ".ts"))
        self.assertEqual(len(eps), 2)

    def test_no_endpoints_in_plain_file(self):
        content = 'def hello():\n    print("hello")'
        eps = _extract_generic_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 0)


class TestGenericEntities(unittest.TestCase):
    """Test estrazione entità cross-linguaggio."""

    def _make_file(self, content, path="models.py", ext=".py"):
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=ext,
            category="altro", priority="media", size_bytes=len(content),
            content=content,
        )

    def test_django_model(self):
        content = 'class Order(models.Model):\n    name = models.CharField(max_length=100)'
        entities = _extract_generic_entities(self._make_file(content))
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "Order")

    def test_sqlalchemy_model(self):
        content = 'class User(Base):\n    __tablename__ = "users"\n    id = Column(Integer, primary_key=True)'
        entities = _extract_generic_entities(self._make_file(content))
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "User")

    def test_typeorm_entity(self):
        content = '@Entity()\nexport class Product {\n    @PrimaryColumn()\n    id: number;\n}'
        entities = _extract_generic_entities(self._make_file(content, "product.entity.ts", ".ts"))
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "Product")

    def test_prisma_model(self):
        content = 'model User {\n  id    Int    @id\n  name  String\n}'
        entities = _extract_generic_entities(self._make_file(content, "schema.prisma", ".prisma"))
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].name, "User")


class TestGenericDeps(unittest.TestCase):
    """Test estrazione dipendenze cross-linguaggio."""

    def _make_file(self, content, path, ext=""):
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=ext,
            category="altro", priority="bassa", size_bytes=len(content),
            content=content,
        )

    def test_requirements_txt(self):
        content = "django==4.2\nrequests>=2.31.0\nflask"
        deps = _extract_generic_deps(self._make_file(content, "requirements.txt"))
        self.assertEqual(len(deps), 3)
        self.assertEqual(deps[0].name, "django")
        self.assertEqual(deps[0].version, "4.2")
        self.assertEqual(deps[0].scope, "pip")
        self.assertEqual(deps[2].name, "flask")

    def test_go_mod(self):
        content = 'module example.com/app\n\ngo 1.21\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.1\n\tgorm.io/gorm v1.25.5\n)'
        deps = _extract_generic_deps(self._make_file(content, "go.mod"))
        self.assertEqual(len(deps), 2)
        self.assertEqual(deps[0].scope, "go")

    def test_cargo_toml(self):
        content = '[package]\nname = "myapp"\n\n[dependencies]\nserde = "1.0"\ntokio = "1.34"'
        deps = _extract_generic_deps(self._make_file(content, "Cargo.toml"))
        self.assertEqual(len(deps), 2)
        self.assertEqual(deps[0].scope, "cargo")

    def test_gemfile(self):
        content = 'gem "rails", "~> 7.0"\ngem "pg"'
        deps = _extract_generic_deps(self._make_file(content, "Gemfile"))
        self.assertEqual(len(deps), 2)
        self.assertEqual(deps[0].name, "rails")
        self.assertEqual(deps[0].scope, "gem")

    def test_composer_json(self):
        content = '{"require": {"laravel/framework": "^10.0", "guzzlehttp/guzzle": "^7.0"}, "require-dev": {"phpunit/phpunit": "^10.0"}}'
        deps = _extract_generic_deps(self._make_file(content, "composer.json"))
        # 2 require + 1 require-dev = 3, minus php* filtering
        self.assertGreaterEqual(len(deps), 2)
        self.assertEqual(deps[0].scope, "composer")

    def test_empty_file(self):
        deps = _extract_generic_deps(self._make_file("", "requirements.txt"))
        self.assertEqual(len(deps), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Chunker
# ═══════════════════════════════════════════════════════════════════════════════

class TestChunker(unittest.TestCase):

    def test_chunks_on_test_project(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        scan_result = scan_project(config)
        plan = create_chunks(scan_result, config)

        self.assertIsInstance(plan, ChunkPlan)
        self.assertGreater(plan.total_chunks, 0)
        self.assertEqual(plan.total_files, scan_result.total_files)

    def test_chunk_respects_budget(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT), chunk_budget=80_000)
        scan_result = scan_project(config)
        plan = create_chunks(scan_result, config)

        budget_chars = config.tokens_to_chars(config.chunk_budget)
        for chunk in plan.chunks:
            self.assertLessEqual(chunk.total_chars, budget_chars)

    def test_small_budget_creates_more_chunks(self):
        config_big = DocGenConfig(project_path=str(TEST_PROJECT), chunk_budget=80_000)
        config_small = DocGenConfig(project_path=str(TEST_PROJECT), chunk_budget=1_000)
        scan_result = scan_project(config_big)

        plan_big = create_chunks(scan_result, config_big)
        plan_small = create_chunks(scan_result, config_small)

        self.assertGreaterEqual(plan_small.total_chunks, plan_big.total_chunks)

    def test_chunk_to_text(self):
        chunk = Chunk(module="test")
        f = ScannedFile(
            path="Test.java", abs_path="/tmp/Test.java", extension=".java",
            category="service", priority="media", size_bytes=20,
            content="public class Test {}",
        )
        chunk.add_file(f)
        text = chunk.to_text()
        self.assertIn("test", text)
        self.assertIn("Test.java", text)
        self.assertIn("public class Test", text)

    def test_cost_estimate(self):
        config = DocGenConfig(project_path=str(TEST_PROJECT))
        scan_result = scan_project(config)
        plan = create_chunks(scan_result, config)
        cost = plan.estimate_total_cost()
        self.assertGreater(cost, 0)
        # Per il test project deve essere sotto $1
        self.assertLess(cost, 1.0)

    def test_empty_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DocGenConfig(project_path=tmpdir)
            scan_result = scan_project(config)
            plan = create_chunks(scan_result, config)
            self.assertEqual(plan.total_chunks, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Renderer
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseTable(unittest.TestCase):

    def test_basic_table(self):
        lines = [
            "| Col1 | Col2 | Col3 |",
            "|------|------|------|",
            "| A    | B    | C    |",
            "| D    | E    | F    |",
        ]
        rows = _parse_table(lines)
        self.assertEqual(len(rows), 3)  # header + 2 righe dati
        self.assertEqual(rows[0], ["Col1", "Col2", "Col3"])

    def test_empty_table(self):
        rows = _parse_table([])
        self.assertEqual(len(rows), 0)

    def test_separator_only(self):
        lines = ["|---|---|"]
        rows = _parse_table(lines)
        self.assertEqual(len(rows), 0)


class TestMarkdownToDocx(unittest.TestCase):

    def test_basic_document(self):
        md = """# Titolo principale

## Sezione 1

Questo è un paragrafo con **testo bold** e *testo italic*.

### Sottosezione 1.1

- Elemento 1
- Elemento 2
- Elemento 3

1. Primo
2. Secondo

| Colonna A | Colonna B |
|-----------|-----------|
| Valore 1  | Valore 2  |

```java
public class Test {}
```

Testo con `inline code` qui.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "test.docx")
            markdown_to_docx(md, output, title="Test Doc", project_name="Test Project")
            self.assertTrue(os.path.exists(output))
            self.assertGreater(os.path.getsize(output), 0)

    def test_empty_markdown(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "empty.docx")
            markdown_to_docx("", output, title="Empty", project_name="Test")
            self.assertTrue(os.path.exists(output))

    def test_headings_all_levels(self):
        md = "# H1\n## H2\n### H3\n#### H4\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "headings.docx")
            markdown_to_docx(md, output)
            self.assertTrue(os.path.exists(output))

    def test_complex_table(self):
        md = """
| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | /api/users | Lista utenti |
| POST | /api/users | Crea utente |
| DELETE | /api/users/{id} | Elimina utente |
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "table.docx")
            markdown_to_docx(md, output)
            self.assertTrue(os.path.exists(output))

    def test_code_block(self):
        md = "```python\nprint('hello')\nx = 42\n```\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "code.docx")
            markdown_to_docx(md, output)
            self.assertTrue(os.path.exists(output))

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "sub", "dir", "test.docx")
            markdown_to_docx("# Test\n", output)
            self.assertTrue(os.path.exists(output))

    def test_separator_line(self):
        md = "Paragrafo 1\n\n---\n\nParagrafo 2\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            output = os.path.join(tmpdir, "sep.docx")
            markdown_to_docx(md, output)
            self.assertTrue(os.path.exists(output))


class TestRenderDocuments(unittest.TestCase):

    def test_render_all_formats(self):
        from docgen.renderer import render_documents
        func_md = "# Specifica Funzionale\n\n## 1. Introduzione\nTesto di test.\n"
        tech_md = "# Specifica Tecnica\n\n## 1. Architettura\nTesto di test.\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            files = render_documents(func_md, tech_md, tmpdir, "Test Project", "all")
            self.assertEqual(len(files), 4)  # 2 MD + 2 DOCX
            for f in files:
                self.assertTrue(os.path.exists(f))
                self.assertGreater(os.path.getsize(f), 0)

    def test_render_md_only(self):
        from docgen.renderer import render_documents
        with tempfile.TemporaryDirectory() as tmpdir:
            files = render_documents("# F\n", "# T\n", tmpdir, "Test", "md")
            self.assertEqual(len(files), 2)
            for f in files:
                self.assertTrue(f.endswith(".md"))

    def test_render_docx_only(self):
        from docgen.renderer import render_documents
        with tempfile.TemporaryDirectory() as tmpdir:
            files = render_documents("# F\n", "# T\n", tmpdir, "Test", "docx")
            self.assertEqual(len(files), 2)
            for f in files:
                self.assertTrue(f.endswith(".docx"))


# ═══════════════════════════════════════════════════════════════════════════════
# Test Prompts
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrompts(unittest.TestCase):

    def test_prompts_are_strings(self):
        from docgen.prompts import SYSTEM_PROMPT, ANALYZE_CHUNK, FUNCTIONAL_DOC, TECHNICAL_DOC
        self.assertIsInstance(SYSTEM_PROMPT, str)
        self.assertIsInstance(ANALYZE_CHUNK, str)
        self.assertIsInstance(FUNCTIONAL_DOC, str)
        self.assertIsInstance(TECHNICAL_DOC, str)

    def test_analyze_chunk_has_placeholders(self):
        from docgen.prompts import ANALYZE_CHUNK
        self.assertIn("{project_name}", ANALYZE_CHUNK)
        self.assertIn("{static_analysis}", ANALYZE_CHUNK)
        self.assertIn("{chunk_content}", ANALYZE_CHUNK)

    def test_functional_doc_has_placeholders(self):
        from docgen.prompts import FUNCTIONAL_DOC
        self.assertIn("{project_name}", FUNCTIONAL_DOC)
        self.assertIn("{module_analyses}", FUNCTIONAL_DOC)

    def test_technical_doc_has_placeholders(self):
        from docgen.prompts import TECHNICAL_DOC
        self.assertIn("{project_name}", TECHNICAL_DOC)
        self.assertIn("{module_analyses}", TECHNICAL_DOC)

    def test_analyze_chunk_format(self):
        from docgen.prompts import ANALYZE_CHUNK
        formatted = ANALYZE_CHUNK.format(
            project_name="Test",
            static_analysis="nessuna",
            chunk_content="codice test",
        )
        self.assertIn("Test", formatted)
        self.assertIn("codice test", formatted)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Generator (solo funzioni helper, no API calls)
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeneratorHelpers(unittest.TestCase):

    def test_smart_truncate_no_op(self):
        from docgen.generator import smart_truncate
        text = "short text"
        self.assertEqual(smart_truncate(text, 10000), text)

    def test_smart_truncate_with_sections(self):
        from docgen.generator import smart_truncate
        text = "### Sezione 1\n" + "A" * 5000 + "\n### Sezione 2\n" + "B" * 5000
        result = smart_truncate(text, 2000)
        self.assertLessEqual(len(result), 10000)  # Dovrebbe essere più corto
        self.assertIn("troncato", result)

    def test_smart_truncate_no_sections(self):
        from docgen.generator import smart_truncate
        text = "A" * 10000
        result = smart_truncate(text, 2000)
        self.assertIn("TRONCATO", result)


# ═══════════════════════════════════════════════════════════════════════════════
# Test CLI (argument parsing)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCLI(unittest.TestCase):

    def test_build_config_defaults(self):
        from docgen.main import build_config
        import argparse
        args = argparse.Namespace(
            project_path=str(TEST_PROJECT),
            name=None,
            output="./test_output",
            format="all",
            model="claude-sonnet-4-20250514",
            dry_run=True,
            max_tokens=200000,
            chunk_budget=80000,
            export_prompts=False,
            llm_bridge=False,
            agent_export=False,
        )
        config = build_config(args)
        self.assertTrue(config.project_path.endswith("test-project"))
        self.assertEqual(config.project_name, "test-project")
        self.assertTrue(config.dry_run)

    def test_build_config_custom_name(self):
        from docgen.main import build_config
        import argparse
        args = argparse.Namespace(
            project_path=str(TEST_PROJECT),
            name="My Project",
            output="./out",
            format="md",
            model="claude-sonnet-4-20250514",
            dry_run=False,
            max_tokens=100000,
            chunk_budget=50000,
            export_prompts=False,
            llm_bridge=False,
            agent_export=False,
        )
        config = build_config(args)
        self.assertEqual(config.project_name, "My Project")
        self.assertEqual(config.output_format, "md")
        self.assertEqual(config.chunk_budget, 50000)

    def test_build_config_invalid_path(self):
        from docgen.main import build_config
        import argparse
        args = argparse.Namespace(
            project_path="/nonexistent/path/xyz",
            name=None,
            output="./out",
            format="all",
            model="claude-sonnet-4-20250514",
            dry_run=True,
            max_tokens=200000,
            chunk_budget=80000,
            export_prompts=False,
            llm_bridge=False,
            agent_export=False,
        )
        with self.assertRaises(SystemExit):
            build_config(args)


# ═══════════════════════════════════════════════════════════════════════════════
# Test export prompts
# ═══════════════════════════════════════════════════════════════════════════════

class TestExportPrompts(unittest.TestCase):

    def test_export_prompts_unified(self):
        """Test esportazione prompt in modalità unificata."""
        from docgen.main import _export_prompts_unified

        config = DocGenConfig(
            project_path=str(TEST_PROJECT),
            project_name="Test Project",
            output_dir=str(TEST_PROJECT / "DocGen"),
            chunk_budget=80_000,
        )
        scan_result = scan_project(config)
        analysis = analyze_project(scan_result)
        chunk_plan = create_chunks(scan_result, config)

        generated = _export_prompts_unified(chunk_plan, analysis, config)

        prompts_dir = TEST_PROJECT / "DocGen" / "prompts"
        self.assertTrue(prompts_dir.exists())

        # System prompt + N chunk + funzionale + tecnica
        expected_min = 1 + chunk_plan.total_chunks + 2
        self.assertEqual(len(generated), expected_min)

        # Verifica file system prompt
        self.assertTrue((prompts_dir / "00_SYSTEM_PROMPT.md").exists())
        # Verifica file funzionale
        self.assertTrue((prompts_dir / "02_SPECIFICA_FUNZIONALE.md").exists())
        # Verifica file tecnica
        self.assertTrue((prompts_dir / "03_SPECIFICA_TECNICA.md").exists())

        # Verifica contenuto system prompt
        sys_content = (prompts_dir / "00_SYSTEM_PROMPT.md").read_text()
        self.assertIn("analista software", sys_content)

        # Verifica contenuto funzionale contiene placeholder
        func_content = (prompts_dir / "02_SPECIFICA_FUNZIONALE.md").read_text()
        self.assertIn("[INSERISCI QUI", func_content)
        self.assertIn("Test Project", func_content)

    def test_export_prompts_unified_chunk_contains_code(self):
        """Verifica che i prompt di chunk contengano il codice sorgente."""
        from docgen.main import _export_prompts_unified

        config = DocGenConfig(
            project_path=str(TEST_PROJECT),
            project_name="Test PA",
            output_dir=str(TEST_PROJECT / "DocGen"),
            chunk_budget=80_000,
        )
        scan_result = scan_project(config)
        analysis = analyze_project(scan_result)
        chunk_plan = create_chunks(scan_result, config)

        _export_prompts_unified(chunk_plan, analysis, config)

        prompts_dir = TEST_PROJECT / "DocGen" / "prompts"
        # Trova il primo file chunk
        chunk_files = sorted(prompts_dir.glob("01_ANALISI_CHUNK_*.md"))
        self.assertGreater(len(chunk_files), 0)

        content = chunk_files[0].read_text()
        # Deve contenere codice sorgente effettivo
        self.assertIn("Modulo:", content)
        self.assertIn("Token stimati:", content)

    def tearDown(self):
        """Pulisce la directory DocGen creata dai test."""
        import shutil
        docgen_dir = TEST_PROJECT / "DocGen"
        if docgen_dir.exists():
            shutil.rmtree(docgen_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# Test integrazione end-to-end (dry-run)
# ═══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd(unittest.TestCase):

    def test_full_pipeline_dry_run(self):
        """Test del pipeline completo Scanner → Analyzer → Chunker."""
        config = DocGenConfig(
            project_path=str(TEST_PROJECT),
            project_name="Gestione Utenti PA",
            chunk_budget=80_000,
        )

        # 1. Scan
        scan_result = scan_project(config)
        self.assertGreater(scan_result.total_files, 5)

        # 2. Analyze
        analysis = analyze_project(scan_result)
        self.assertGreater(len(analysis.endpoints), 5)
        self.assertEqual(len(analysis.entities), 1)
        self.assertEqual(analysis.entities[0].name, "Utente")
        self.assertGreater(len(analysis.routes), 0)
        self.assertGreater(len(analysis.components), 0)
        self.assertIn("postgresql", analysis.db_info.url)

        # 3. Chunk
        plan = create_chunks(scan_result, config)
        self.assertEqual(plan.total_chunks, 2)  # backend + frontend
        self.assertEqual(plan.total_files, scan_result.total_files)

        # 4. Verify chunk content is serializable
        for chunk in plan.chunks:
            text = chunk.to_text()
            self.assertIsInstance(text, str)
            self.assertGreater(len(text), 0)

        # 5. Verify summary is usable in prompts
        summary = analysis.summary_text()
        from docgen.prompts import ANALYZE_CHUNK
        prompt = ANALYZE_CHUNK.format(
            project_name="Test",
            static_analysis=summary,
            chunk_content=plan.chunks[0].to_text(),
        )
        self.assertIsInstance(prompt, str)
        self.assertGreater(len(prompt), 100)

    def test_render_pipeline(self):
        """Test del rendering MD → DOCX."""
        from docgen.renderer import render_documents
        func_md = """# Specifica Funzionale — Test Project

## 1. Introduzione
### 1.1 Scopo del documento
Questo documento descrive i requisiti funzionali.

## 2. Requisiti funzionali
**[FUN-001] Gestione utenti**
- Descrizione: Il sistema deve permettere la gestione degli utenti
- Priorità: Alta

| ID | Requisito | Priorità |
|----|-----------|----------|
| FUN-001 | Gestione utenti | Alta |
| FUN-002 | Ricerca | Media |

## 3. Modello dati

```mermaid
erDiagram
    UTENTE {
        Long id
        String nome
    }
```
"""
        tech_md = """# Specifica Tecnica — Test Project

## 1. Architettura

### Stack tecnologico

| Tecnologia | Versione |
|------------|----------|
| Spring Boot | 3.2.0 |
| Angular | 17.0 |

## 2. API REST

| Metodo | Path | Descrizione |
|--------|------|-------------|
| GET | /api/utenti | Lista |
| POST | /api/utenti | Crea |
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            files = render_documents(func_md, tech_md, tmpdir, "Test Project", "all")
            self.assertEqual(len(files), 4)
            # Verifica che i DOCX abbiano dimensioni ragionevoli
            for f in files:
                if f.endswith(".docx"):
                    size = os.path.getsize(f)
                    self.assertGreater(size, 5000, f"{f} troppo piccolo: {size}")


# ═══════════════════════════════════════════════════════════════════════════════
# Test Hybrid (multi-microservizio)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHybridConfig(unittest.TestCase):

    def test_large_project_thresholds_exist(self):
        self.assertGreaterEqual(LARGE_PROJECT_MIN_MODULES, 2)
        self.assertGreaterEqual(LARGE_PROJECT_MIN_CHUNKS, 4)


class TestHybridDetection(unittest.TestCase):

    def _make_scan_result(self, modules: list[str], files_per_module: int = 5) -> ScanResult:
        """Crea un ScanResult con N moduli e file di test."""
        result = ScanResult()
        for mod in modules:
            for i in range(files_per_module):
                result.files.append(ScannedFile(
                    path=f"{mod}/Src{i}.java",
                    abs_path=f"/tmp/{mod}/Src{i}.java",
                    extension=".java",
                    category="altro",
                    priority="media",
                    size_bytes=1000,
                    module=mod,
                    content="public class Src" + str(i) + " {}",
                ))
        result.modules = modules
        return result

    def test_is_large_project_true(self):
        from docgen.main import _is_large_project
        config = DocGenConfig(chunk_budget=80_000)
        modules = [f"service-{i}" for i in range(5)]
        # Big content per file to force multiple chunks per module
        scan_result = self._make_scan_result(modules, files_per_module=20)
        # Override content to be large enough to fill chunks
        for f in scan_result.files:
            f.content = "x" * 50_000  # ~14K tokens per file → multiple chunks per module
        chunk_plan = create_chunks(scan_result, config)
        self.assertTrue(_is_large_project(scan_result, chunk_plan))

    def test_is_large_project_false_few_modules(self):
        from docgen.main import _is_large_project
        config = DocGenConfig(chunk_budget=80_000)
        scan_result = self._make_scan_result(["backend"], files_per_module=5)
        chunk_plan = create_chunks(scan_result, config)
        self.assertFalse(_is_large_project(scan_result, chunk_plan))


class TestCreateModuleChunkPlans(unittest.TestCase):

    def _make_scan_result(self, modules: list[str], content_size: int = 5000) -> ScanResult:
        result = ScanResult()
        for mod in modules:
            for i in range(3):
                result.files.append(ScannedFile(
                    path=f"{mod}/File{i}.java",
                    abs_path=f"/tmp/{mod}/File{i}.java",
                    extension=".java",
                    category="service",
                    priority="alta",
                    size_bytes=content_size,
                    module=mod,
                    content="x" * content_size,
                ))
        result.modules = modules
        return result

    def test_creates_plan_per_module(self):
        from docgen.main import _create_module_chunk_plans
        config = DocGenConfig(chunk_budget=80_000)
        modules = ["api-a", "api-b", "web"]
        scan_result = self._make_scan_result(modules)
        plans = _create_module_chunk_plans(scan_result, config)

        self.assertEqual(len(plans), 3)
        self.assertIn("api-a", plans)
        self.assertIn("api-b", plans)
        self.assertIn("web", plans)

    def test_each_plan_has_only_its_files(self):
        from docgen.main import _create_module_chunk_plans
        config = DocGenConfig(chunk_budget=80_000)
        scan_result = self._make_scan_result(["svc-1", "svc-2"])
        plans = _create_module_chunk_plans(scan_result, config)

        for module_name, plan in plans.items():
            for chunk in plan.chunks:
                for f in chunk.files:
                    self.assertEqual(f.module, module_name)


class TestEstimateHybridCost(unittest.TestCase):

    def test_cost_positive(self):
        from docgen.main import _estimate_hybrid_cost
        plan_a = ChunkPlan(chunks=[Chunk(module="a", total_tokens_est=5000)])
        plan_b = ChunkPlan(chunks=[Chunk(module="b", total_tokens_est=3000)])
        cost = _estimate_hybrid_cost({"a": plan_a, "b": plan_b})
        self.assertGreater(cost, 0)

    def test_more_modules_more_cost(self):
        from docgen.main import _estimate_hybrid_cost
        plan_1 = {"a": ChunkPlan(chunks=[Chunk(module="a", total_tokens_est=5000)])}
        plan_3 = {
            "a": ChunkPlan(chunks=[Chunk(module="a", total_tokens_est=5000)]),
            "b": ChunkPlan(chunks=[Chunk(module="b", total_tokens_est=5000)]),
            "c": ChunkPlan(chunks=[Chunk(module="c", total_tokens_est=5000)]),
        }
        self.assertGreater(_estimate_hybrid_cost(plan_3), _estimate_hybrid_cost(plan_1))


class TestRenderDocumentsHybrid(unittest.TestCase):

    def test_renders_per_module_dirs(self):
        results = {
            "api-users": ("# Funzionale Users", "# Tecnica Users"),
            "api-orders": ("# Funzionale Orders", "# Tecnica Orders"),
            "_architettura_sistema": ("# Architettura di Sistema", ""),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            generated = render_documents_hybrid(results, tmpdir, "TestProject", "md")

            # Check per-module dirs exist
            self.assertTrue(Path(tmpdir, "api-users").is_dir())
            self.assertTrue(Path(tmpdir, "api-orders").is_dir())

            # Architecture in root
            arch_files = [f for f in generated if "ARCHITETTURA" in f]
            self.assertEqual(len(arch_files), 1)
            self.assertIn(tmpdir, arch_files[0])  # Not in a subdirectory

            # Module docs in subdirs
            user_files = [f for f in generated if "api-users" in f]
            self.assertEqual(len(user_files), 2)  # func + tech

    def test_renders_docx_format(self):
        results = {
            "svc-a": ("# Funzionale A\n\nContenuto.", "# Tecnica A\n\nContenuto."),
            "_architettura_sistema": ("# Architettura\n\nContenuto.", ""),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            generated = render_documents_hybrid(results, tmpdir, "Test", "all")
            docx_files = [f for f in generated if f.endswith(".docx")]
            md_files = [f for f in generated if f.endswith(".md")]
            # 1 module * 2 (func+tech) + 1 arch = 3 docx + 3 md
            self.assertEqual(len(docx_files), 3)
            self.assertEqual(len(md_files), 3)


class TestNewPrompts(unittest.TestCase):

    def test_system_architecture_doc_has_placeholders(self):
        from docgen.prompts import SYSTEM_ARCHITECTURE_DOC
        self.assertIn("{project_name}", SYSTEM_ARCHITECTURE_DOC)
        self.assertIn("{static_analysis}", SYSTEM_ARCHITECTURE_DOC)
        self.assertIn("{service_summaries}", SYSTEM_ARCHITECTURE_DOC)

    def test_service_summary_has_placeholders(self):
        from docgen.prompts import SERVICE_SUMMARY
        self.assertIn("{service_name}", SERVICE_SUMMARY)
        self.assertIn("{module_analyses}", SERVICE_SUMMARY)

    def test_system_architecture_doc_has_key_sections(self):
        from docgen.prompts import SYSTEM_ARCHITECTURE_DOC
        self.assertIn("Mappa dei microservizi", SYSTEM_ARCHITECTURE_DOC)
        self.assertIn("Integrazioni e comunicazioni", SYSTEM_ARCHITECTURE_DOC)
        self.assertIn("Flussi operativi", SYSTEM_ARCHITECTURE_DOC)
        self.assertIn("Mermaid", SYSTEM_ARCHITECTURE_DOC)


class TestPrintHybridPlan(unittest.TestCase):

    def test_no_crash(self):
        """Verifica che _print_hybrid_plan non sollevi eccezioni."""
        from docgen.main import _print_hybrid_plan
        plans = {
            "svc-a": ChunkPlan(chunks=[Chunk(module="svc-a", total_tokens_est=5000)]),
            "svc-b": ChunkPlan(chunks=[Chunk(module="svc-b", total_tokens_est=3000)]),
        }
        # Just check it doesn't raise
        _print_hybrid_plan(plans)


# ═══════════════════════════════════════════════════════════════════════════════
# Test .NET / ASP.NET Core / EF Core
# ═══════════════════════════════════════════════════════════════════════════════

class TestDotnetClassification(unittest.TestCase):
    """Classificazione file C#."""

    def test_apicontroller(self):
        content = '[ApiController]\n[Route("api/[controller]")]\npublic class UsersController : ControllerBase {}'
        self.assertEqual(_classify_file("Controllers/UsersController.cs", ".cs", content), "controller")

    def test_controllerbase_inheritance(self):
        content = 'public class OrdersController : ControllerBase\n{\n}'
        self.assertEqual(_classify_file("API/OrdersController.cs", ".cs", content), "controller")

    def test_dbcontext(self):
        content = 'public class AppDbContext : DbContext\n{\n    public DbSet<User> Users { get; set; }\n}'
        self.assertEqual(_classify_file("Data/AppDbContext.cs", ".cs", content), "dbcontext")

    def test_entity_with_table_attr(self):
        content = '[Table("utenti")]\npublic class Utente\n{\n    [Key]\n    public int Id { get; set; }\n}'
        self.assertEqual(_classify_file("Domain/Utente.cs", ".cs", content), "entity")

    def test_entity_with_key_attr(self):
        content = 'public class Order\n{\n    [Key]\n    public int Id { get; set; }\n}'
        self.assertEqual(_classify_file("Models/Order.cs", ".cs", content), "entity")

    def test_service_interface(self):
        content = 'public interface IUserService\n{\n    Task<User> GetById(int id);\n}'
        self.assertEqual(_classify_file("Services/IUserService.cs", ".cs", content), "service")

    def test_migration(self):
        content = 'public partial class InitialCreate : Migration\n{\n}'
        self.assertEqual(_classify_file("Migrations/20240101_InitialCreate.cs", ".cs", content), "migration")

    def test_middleware(self):
        content = 'public class AuthMiddleware\n{\n}'
        self.assertEqual(_classify_file("Middleware/AuthMiddleware.cs", ".cs", content), "middleware")

    def test_csproj_build_config(self):
        self.assertEqual(_classify_file("MyProject/MyProject.csproj", ".csproj", ""), "build_config")

    def test_sln_build_config(self):
        self.assertEqual(_classify_file("MyApp.sln", ".sln", ""), "build_config")

    def test_appsettings_app_config(self):
        self.assertEqual(
            _classify_file("appsettings.json", ".json", '{"ConnectionStrings":{}}'),
            "app_config",
        )


class TestDotnetEndpointExtraction(unittest.TestCase):
    """Estrazione endpoint REST da controller ASP.NET Core."""

    def _make_file(self, content: str) -> ScannedFile:
        return ScannedFile(
            path="Controllers/UsersController.cs",
            abs_path="/tmp/Controllers/UsersController.cs",
            extension=".cs",
            category="controller",
            priority="alta",
            size_bytes=len(content),
            content=content,
        )

    def test_basic_endpoints(self):
        content = '''
[ApiController]
[Route("api/[controller]")]
public class UsersController : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAll()
    {
        return Ok();
    }

    [HttpGet("{id}")]
    public async Task<IActionResult> GetById(int id)
    {
        return Ok();
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] UserDto dto)
    {
        return Ok();
    }

    [HttpPut("{id}")]
    public async Task<ActionResult<User>> Update(int id)
    {
        return Ok();
    }

    [HttpDelete("{id}")]
    public IActionResult Delete(int id)
    {
        return Ok();
    }
}
'''
        eps = _extract_dotnet_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 5)
        methods = [ep.method for ep in eps]
        self.assertIn("GET", methods)
        self.assertIn("POST", methods)
        self.assertIn("PUT", methods)
        self.assertIn("DELETE", methods)

    def test_controller_route_substitution(self):
        content = '''
[Route("api/[controller]")]
public class OrdersController : ControllerBase
{
    [HttpGet]
    public IActionResult GetAll() { return Ok(); }
}
'''
        eps = _extract_dotnet_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertIn("orders", eps[0].path.lower())
        self.assertNotIn("[controller]", eps[0].path)

    def test_explicit_route(self):
        content = '''
[Route("api/v2/users")]
public class UsersController : ControllerBase
{
    [HttpGet("active")]
    public IActionResult GetActive() { return Ok(); }
}
'''
        eps = _extract_dotnet_endpoints(self._make_file(content))
        self.assertEqual(len(eps), 1)
        self.assertIn("api/v2/users", eps[0].path)
        self.assertIn("active", eps[0].path)

    def test_handler_name_extracted(self):
        content = '''
[Route("api/items")]
public class ItemsController : ControllerBase
{
    [HttpGet]
    public async Task<ActionResult<List<Item>>> ListItems()
    {
        return Ok();
    }
}
'''
        eps = _extract_dotnet_endpoints(self._make_file(content))
        self.assertEqual(eps[0].handler, "ListItems")


class TestDotnetEntityExtraction(unittest.TestCase):
    """Estrazione entità EF Core."""

    def _make_file(self, content: str, path: str = "Domain/Entity.cs") -> ScannedFile:
        return ScannedFile(
            path=path, abs_path=f"/tmp/{path}", extension=".cs",
            category="entity", priority="alta", size_bytes=len(content), content=content,
        )

    def test_entity_with_table_and_key(self):
        content = '''
[Table("utenti")]
public class Utente
{
    [Key]
    public int Id { get; set; }
    public string Nome { get; set; }
    public string Cognome { get; set; }
    public DateTime DataNascita { get; set; }
}
'''
        entity = _extract_dotnet_entity(self._make_file(content))
        self.assertIsNotNone(entity)
        self.assertEqual(entity.name, "Utente")
        self.assertEqual(entity.table, "utenti")
        self.assertEqual(len(entity.fields), 4)
        # Verifica che [Key] sia trovato su Id
        id_field = [f for f in entity.fields if "Id" in f]
        self.assertTrue(any("[Key]" in f for f in id_field))

    def test_entity_without_table(self):
        content = '''
public class Product
{
    public int Id { get; set; }
    public string Name { get; set; }
    public decimal Price { get; set; }
}
'''
        entity = _extract_dotnet_entity(self._make_file(content))
        self.assertIsNotNone(entity)
        self.assertEqual(entity.name, "Product")
        self.assertEqual(entity.table, "")
        self.assertEqual(len(entity.fields), 3)

    def test_nullable_types(self):
        content = '''
public class Contact
{
    public int Id { get; set; }
    public string? Email { get; set; }
    public int? PhoneNumber { get; set; }
}
'''
        entity = _extract_dotnet_entity(self._make_file(content))
        self.assertIsNotNone(entity)
        types = [f.split()[0] for f in entity.fields]
        self.assertIn("string?", types)
        self.assertIn("int?", types)


class TestDbContextExtraction(unittest.TestCase):

    def test_dbset_entities(self):
        content = '''
public class AppDbContext : DbContext
{
    public DbSet<User> Users { get; set; }
    public DbSet<Order> Orders { get; set; }
    public DbSet<Product> Products { get; set; }
}
'''
        file = ScannedFile(
            path="Data/AppDbContext.cs", abs_path="/tmp/Data/AppDbContext.cs",
            extension=".cs", category="dbcontext", priority="alta",
            size_bytes=len(content), content=content,
        )
        entities = _extract_dbcontext_entities(file)
        self.assertEqual(len(entities), 3)
        names = {e.name for e in entities}
        self.assertEqual(names, {"User", "Order", "Product"})
        # Table name from property name
        tables = {e.table for e in entities}
        self.assertEqual(tables, {"Users", "Orders", "Products"})


class TestNugetExtraction(unittest.TestCase):

    def test_extract_packages(self):
        content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />
    <PackageReference Include="Swashbuckle.AspNetCore" Version="6.5.0" />
    <PackageReference Include="Serilog.AspNetCore" Version="7.0.0" />
  </ItemGroup>
</Project>'''
        file = ScannedFile(
            path="MyApi/MyApi.csproj", abs_path="/tmp/MyApi/MyApi.csproj",
            extension=".csproj", category="build_config", priority="alta",
            size_bytes=len(content), content=content,
        )
        deps = _extract_nuget_deps(file)
        self.assertEqual(len(deps), 3)
        self.assertEqual(deps[0].name, "Microsoft.EntityFrameworkCore")
        self.assertEqual(deps[0].version, "8.0.0")
        self.assertEqual(deps[0].scope, "nuget")

    def test_no_packages(self):
        content = '<Project Sdk="Microsoft.NET.Sdk.Web"></Project>'
        file = ScannedFile(
            path="Empty.csproj", abs_path="/tmp/Empty.csproj",
            extension=".csproj", category="build_config", priority="alta",
            size_bytes=len(content), content=content,
        )
        self.assertEqual(len(_extract_nuget_deps(file)), 0)


class TestAppsettingsDbExtraction(unittest.TestCase):

    def test_sql_server(self):
        content = '{"ConnectionStrings": {"DefaultConnection": "Server=localhost;Database=MyDb;Trusted_Connection=true;"}}'
        file = ScannedFile(
            path="appsettings.json", abs_path="/tmp/appsettings.json",
            extension=".json", category="app_config", priority="alta",
            size_bytes=len(content), content=content,
        )
        db = _extract_db_info_appsettings(file)
        self.assertIn("Server=localhost", db.url)
        self.assertEqual(db.driver, "SQL Server")

    def test_postgresql(self):
        content = '{"ConnectionStrings": {"DefaultConnection": "Host=localhost;Port=5432;Database=mydb;Username=admin;"}}'
        file = ScannedFile(
            path="appsettings.json", abs_path="/tmp/appsettings.json",
            extension=".json", category="app_config", priority="alta",
            size_bytes=len(content), content=content,
        )
        db = _extract_db_info_appsettings(file)
        self.assertEqual(db.driver, "PostgreSQL")

    def test_no_connection_strings(self):
        content = '{"Logging": {"LogLevel": {"Default": "Information"}}}'
        file = ScannedFile(
            path="appsettings.json", abs_path="/tmp/appsettings.json",
            extension=".json", category="app_config", priority="alta",
            size_bytes=len(content), content=content,
        )
        db = _extract_db_info_appsettings(file)
        self.assertEqual(db.url, "")

    def test_invalid_json(self):
        file = ScannedFile(
            path="appsettings.json", abs_path="/tmp/appsettings.json",
            extension=".json", category="app_config", priority="alta",
            size_bytes=10, content="not json",
        )
        db = _extract_db_info_appsettings(file)
        self.assertEqual(db.url, "")


class TestDotnetModuleDetection(unittest.TestCase):

    def test_csproj_detection(self):
        """Verifica che _detect_module riconosca progetti con .csproj."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Crea struttura: MyApi/MyApi.csproj + MyApi/Controllers/Test.cs
            api_dir = os.path.join(tmpdir, "MyApi")
            os.makedirs(os.path.join(api_dir, "Controllers"))
            Path(os.path.join(api_dir, "MyApi.csproj")).write_text("<Project/>")
            Path(os.path.join(api_dir, "Controllers", "Test.cs")).write_text("")

            module = _detect_module("MyApi/Controllers/Test.cs", tmpdir)
            self.assertEqual(module, "MyApi")

    def test_cs_backend_fallback(self):
        """Se non c'è csproj nella prima cartella, .cs → backend."""
        module = _detect_module("src/Class1.cs", "/nonexistent")
        self.assertEqual(module, "backend")


class TestDotnetSummaryText(unittest.TestCase):

    def test_nuget_deps_in_summary(self):
        from docgen.analyzer import Dependency
        analysis = ProjectAnalysis()
        analysis.nuget_deps = [
            Dependency(name="Microsoft.EntityFrameworkCore", version="8.0.0", scope="nuget"),
        ]
        text = analysis.summary_text()
        self.assertIn("NuGet", text)
        self.assertIn("Microsoft.EntityFrameworkCore", text)


class TestDotnetAnalyzeProjectIntegration(unittest.TestCase):
    """Test integrazione: analyze_project con file C#."""

    def test_full_dotnet_analysis(self):
        controller_content = '''
[ApiController]
[Route("api/[controller]")]
public class UsersController : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAll() { return Ok(); }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreateUserDto dto) { return Ok(); }
}
'''
        entity_content = '''
[Table("users")]
public class User
{
    [Key]
    public int Id { get; set; }
    public string Name { get; set; }
    public string Email { get; set; }
}
'''
        dbcontext_content = '''
public class AppDbContext : DbContext
{
    public DbSet<User> Users { get; set; }
    public DbSet<Role> Roles { get; set; }
}
'''
        csproj_content = '''<Project Sdk="Microsoft.NET.Sdk.Web">
  <ItemGroup>
    <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.0" />
  </ItemGroup>
</Project>'''
        appsettings_content = '{"ConnectionStrings": {"Default": "Server=db.example.com;Database=UsersDb;"}}'

        result = ScanResult()
        result.files = [
            ScannedFile(path="Controllers/UsersController.cs", abs_path="/tmp/c.cs",
                        extension=".cs", category="controller", priority="alta",
                        size_bytes=len(controller_content), content=controller_content),
            ScannedFile(path="Domain/User.cs", abs_path="/tmp/u.cs",
                        extension=".cs", category="entity", priority="alta",
                        size_bytes=len(entity_content), content=entity_content),
            ScannedFile(path="Data/AppDbContext.cs", abs_path="/tmp/d.cs",
                        extension=".cs", category="dbcontext", priority="alta",
                        size_bytes=len(dbcontext_content), content=dbcontext_content),
            ScannedFile(path="MyApi.csproj", abs_path="/tmp/p.csproj",
                        extension=".csproj", category="build_config", priority="alta",
                        size_bytes=len(csproj_content), content=csproj_content),
            ScannedFile(path="appsettings.json", abs_path="/tmp/a.json",
                        extension=".json", category="app_config", priority="alta",
                        size_bytes=len(appsettings_content), content=appsettings_content),
        ]

        analysis = analyze_project(result)

        # Endpoint
        self.assertEqual(len(analysis.endpoints), 2)
        self.assertEqual(analysis.endpoints[0].method, "GET")

        # Entità (User da entity file + Role da DbContext, User non duplicato)
        entity_names = {e.name for e in analysis.entities}
        self.assertIn("User", entity_names)
        self.assertIn("Role", entity_names)

        # NuGet
        self.assertEqual(len(analysis.nuget_deps), 1)
        self.assertIn("EntityFrameworkCore", analysis.nuget_deps[0].name)

        # DB
        self.assertIn("db.example.com", analysis.db_info.url)
        self.assertEqual(analysis.db_info.driver, "SQL Server")


# ═══════════════════════════════════════════════════════════════════════════════
# Test Agent Export
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentExport(unittest.TestCase):
    """Test per la modalità --agent-export."""

    def setUp(self):
        self.config = DocGenConfig(
            project_path=str(TEST_PROJECT),
            project_name="Test PA Project",
            output_dir=str(TEST_PROJECT / "DocGen"),
            agent_export=True,
        )
        self.scan_result = scan_project(self.config)
        self.analysis = analyze_project(self.scan_result)

    def tearDown(self):
        docgen_dir = TEST_PROJECT / "DocGen"
        if docgen_dir.exists():
            shutil.rmtree(docgen_dir)

    def test_context_md_generated(self):
        from docgen.main import _generate_context_md
        md = _generate_context_md(self.scan_result, self.analysis, self.config, False, None)
        self.assertIn("Test PA Project", md)
        self.assertIn("Struttura directory", md)
        self.assertIn("Statistiche", md)
        self.assertIn("File classificati per urgenza", md)
        self.assertIn("Istruzioni per la generazione", md)
        self.assertIn("Template: Specifica Funzionale", md)
        self.assertIn("Template: Specifica Tecnica", md)

    def test_context_md_contains_endpoints(self):
        from docgen.main import _generate_context_md
        md = _generate_context_md(self.scan_result, self.analysis, self.config, False, None)
        self.assertIn("Endpoint REST", md)
        self.assertIn("/api/utenti", md)

    def test_context_md_contains_entities(self):
        from docgen.main import _generate_context_md
        md = _generate_context_md(self.scan_result, self.analysis, self.config, False, None)
        self.assertIn("Utente", md)

    def test_context_md_has_file_paths(self):
        from docgen.main import _generate_context_md
        md = _generate_context_md(self.scan_result, self.analysis, self.config, False, None)
        # Deve contenere path relativi dei file
        self.assertIn("Controller", md)
        self.assertIn(".java", md)

    def test_context_md_no_source_code(self):
        """Il context.md NON deve contenere codice sorgente incollato."""
        from docgen.main import _generate_context_md
        md = _generate_context_md(self.scan_result, self.analysis, self.config, False, None)
        # Non deve contenere blocchi di codice Java
        self.assertNotIn("public class UtenteController", md)
        self.assertNotIn("@RestController", md)
        self.assertNotIn("@Entity", md)

    def test_files_json_generated(self):
        from docgen.main import _generate_files_json
        data = _generate_files_json(self.scan_result, self.analysis, self.config, False)
        self.assertEqual(data["project_name"], "Test PA Project")
        self.assertIn("modules", data)
        self.assertIsInstance(data["files"], list)
        self.assertGreater(len(data["files"]), 0)
        self.assertIsInstance(data["endpoints"], list)
        self.assertIsInstance(data["entities"], list)

    def test_files_json_has_priorities_as_strings(self):
        from docgen.main import _generate_files_json
        data = _generate_files_json(self.scan_result, self.analysis, self.config, False)
        for f in data["files"]:
            self.assertIn(f["priority"], ("alta", "media", "bassa"))

    def test_files_json_has_all_files(self):
        from docgen.main import _generate_files_json
        data = _generate_files_json(self.scan_result, self.analysis, self.config, False)
        self.assertEqual(len(data["files"]), self.scan_result.total_files)

    def test_agent_export_writes_files(self):
        from docgen.main import _agent_export
        _agent_export(self.scan_result, self.analysis, self.config, False, None)

        out_dir = TEST_PROJECT / "DocGen"
        self.assertTrue((out_dir / "docgen_context.md").exists())
        self.assertTrue((out_dir / "docgen_files.json").exists())
        self.assertTrue((out_dir / "docgen_index.md").exists())

        # Verifica JSON è valido
        with open(out_dir / "docgen_files.json") as f:
            data = json.load(f)
        self.assertEqual(data["project_name"], "Test PA Project")

    def test_hybrid_context_md_has_architecture_template(self):
        """Per progetti multi-servizio, il context deve avere il template architettura."""
        from docgen.main import _generate_context_md, _create_module_chunk_plans
        module_plans = _create_module_chunk_plans(self.scan_result, self.config)
        md = _generate_context_md(self.scan_result, self.analysis, self.config, True, module_plans)
        self.assertIn("Template: Architettura di Sistema", md)
        self.assertIn("specifica_funzionale_completa.md", md)
        self.assertIn("specifica_tecnica_completa.md", md)


if __name__ == "__main__":
    unittest.main()
