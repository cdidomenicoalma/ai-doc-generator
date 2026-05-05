#!/usr/bin/env python3
"""DocGen — Generatore automatico di documentazione da codebase.

Uso:
    python -m docgen ./mio-progetto --dry-run
    python -m docgen ./mio-progetto -n "Sistema Protocollo" -o ./output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import DocGenConfig, LARGE_PROJECT_MIN_MODULES, LARGE_PROJECT_MIN_CHUNKS
from .scanner import scan_project, ScanResult
from .analyzer import analyze_project, ProjectAnalysis
from .chunker import create_chunks, ChunkPlan
from .prompts import (
    SYSTEM_PROMPT, ANALYZE_CHUNK, FUNCTIONAL_DOC, TECHNICAL_DOC,
    SYSTEM_ARCHITECTURE_DOC, SERVICE_SUMMARY,
    TEST_DOCUMENT_TEMPLATE,
)
from .generator import smart_truncate
from . import modes as _modes

console = Console()

# File temporanei dell'agent-export da rimuovere con --cleanup
AGENT_EXPORT_TEMP_FILES = [
    "analisi_statica.md",
    "struttura_progetto.txt",
    "docgen_files.json",
    "docgen_index.md",
    "docgen_instructions.md",
]
AGENT_EXPORT_TEMP_PATTERNS = [
    "docgen_context_*.md",
    "docgen_context.md",
]


def _print_banner() -> None:
    console.print(Panel.fit(
        "[bold blue]DocGen[/bold blue] — Generatore Automatico di Documentazione\n"
        "[dim]Analizza codebase e genera documentazione professionale[/dim]",
        border_style="blue",
    ))


def _print_scan_stats(result: ScanResult, config: DocGenConfig) -> None:
    """Stampa statistiche della scansione."""
    console.print(f"\n[bold]📁 Statistiche scansione[/bold]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column()
    table.add_row("File trovati", str(result.total_files))
    table.add_row("Dimensione totale", f"{result.total_size / 1024:.1f} KB")
    table.add_row("Caratteri totali", f"{result.total_chars:,}")
    table.add_row("Token stimati", f"{config.chars_to_tokens(result.total_chars):,}")
    table.add_row("Moduli rilevati", ", ".join(result.modules) or "nessuno")
    table.add_row("File saltati (troppo grandi)", str(result.skipped_count))
    table.add_row("Errori lettura", str(result.error_count))
    console.print(table)

    # Top estensioni
    top_ext = result.top_extensions(10)
    if top_ext:
        console.print(f"\n[bold]📊 Top estensioni[/bold]")
        ext_table = Table(show_header=True, header_style="bold")
        ext_table.add_column("Estensione")
        ext_table.add_column("File", justify="right")
        for ext, count in top_ext:
            ext_table.add_row(ext or "(nessuna)", str(count))
        console.print(ext_table)


def _print_category_table(result: ScanResult) -> None:
    """Stampa tabella file per categoria."""
    console.print(f"\n[bold]🏷️  File per categoria[/bold]")
    by_cat = result.files_by_category()

    table = Table(show_header=True, header_style="bold")
    table.add_column("Categoria")
    table.add_column("File", justify="right")
    table.add_column("Esempi")

    for cat in sorted(by_cat.keys()):
        files = by_cat[cat]
        examples = ", ".join(f.path for f in files[:3])
        if len(files) > 3:
            examples += f" (+{len(files) - 3})"
        table.add_row(cat, str(len(files)), examples)

    console.print(table)


def _print_analysis(analysis: ProjectAnalysis) -> None:
    """Stampa risultati dell'analisi statica."""
    console.print(f"\n[bold]🔍 Analisi statica[/bold]")

    if analysis.endpoints:
        console.print(f"\n  [cyan]Endpoint REST:[/cyan] {len(analysis.endpoints)}")
        ep_table = Table(show_header=True, header_style="bold", padding=(0, 1))
        ep_table.add_column("Metodo", style="green")
        ep_table.add_column("Path")
        ep_table.add_column("Handler")
        ep_table.add_column("File", style="dim")
        for ep in analysis.endpoints:
            ep_table.add_row(ep.method, ep.path, ep.handler, ep.file)
        console.print(ep_table)

    if analysis.entities:
        console.print(f"\n  [cyan]Entità JPA:[/cyan] {len(analysis.entities)}")
        for ent in analysis.entities:
            table_info = f" → {ent.table}" if ent.table else ""
            console.print(f"    • {ent.name}{table_info} ({len(ent.fields)} campi)")

    if analysis.routes:
        console.print(f"\n  [cyan]Route Angular:[/cyan] {len(analysis.routes)}")
        for r in analysis.routes:
            lazy = " [LAZY]" if r.lazy else ""
            console.print(f"    • /{r.path} → {r.component}{lazy}")

    if analysis.components:
        console.print(f"\n  [cyan]Componenti Angular:[/cyan] {len(analysis.components)}")
        for c in analysis.components:
            console.print(f"    • {c.name} ({c.selector})")

    if analysis.maven_deps:
        console.print(f"\n  [cyan]Dipendenze Maven:[/cyan] {len(analysis.maven_deps)}")
        for d in analysis.maven_deps[:10]:
            console.print(f"    • {d.name}:{d.version}")
        if len(analysis.maven_deps) > 10:
            console.print(f"    ... +{len(analysis.maven_deps) - 10} altre")

    if analysis.npm_deps:
        console.print(f"\n  [cyan]Dipendenze NPM:[/cyan] {len(analysis.npm_deps)}")
        for d in analysis.npm_deps[:10]:
            console.print(f"    • {d.name}@{d.version}")
        if len(analysis.npm_deps) > 10:
            console.print(f"    ... +{len(analysis.npm_deps) - 10} altre")

    if analysis.db_info.url:
        console.print(f"\n  [cyan]Database:[/cyan]")
        console.print(f"    URL: {analysis.db_info.url}")
        if analysis.db_info.driver:
            console.print(f"    Driver: {analysis.db_info.driver}")
        if analysis.db_info.ddl_auto:
            console.print(f"    DDL Auto: {analysis.db_info.ddl_auto}")
        if analysis.db_info.port:
            console.print(f"    Server Port: {analysis.db_info.port}")


def _print_chunk_plan(plan: ChunkPlan, analysis_tokens: int = 0) -> None:
    """Stampa il piano dei chunk."""
    console.print(f"\n[bold]📦 Piano dei chunk[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Modulo")
    table.add_column("File", justify="right")
    table.add_column("Token est.", justify="right")

    for i, chunk in enumerate(plan.chunks, 1):
        table.add_row(
            str(i),
            chunk.module,
            str(len(chunk.files)),
            f"{chunk.total_tokens_est:,}",
        )

    console.print(table)
    console.print(f"\n  Chunk totali: {plan.total_chunks}")
    console.print(f"  File totali: {plan.total_files}")
    console.print(f"  Token input stimati: {plan.total_input_tokens:,}")
    console.print(f"  [bold]Costo stimato: ${plan.estimate_total_cost(analysis_tokens):.4f}[/bold]")


def _is_large_project(scan_result: ScanResult, chunk_plan: ChunkPlan) -> bool:
    """Rileva se il progetto è grande abbastanza per suggerire la modalità ibrida.

    Un progetto è considerato multi-microservizio se ha abbastanza moduli distinti
    (rilevati via .sln, pom.xml, ecc.) OPPURE se ha molti chunk anche con un solo modulo.
    """
    n_modules = len(scan_result.modules)
    n_chunks = chunk_plan.total_chunks
    # Moduli espliciti sufficienti → hybrid indipendentemente dai chunk
    if n_modules >= LARGE_PROJECT_MIN_MODULES:
        return True
    # Singolo modulo ma molto grande → hybrid per volume
    return n_chunks >= LARGE_PROJECT_MIN_CHUNKS


def _create_module_chunk_plans(
    scan_result: ScanResult,
    config: DocGenConfig,
) -> dict[str, ChunkPlan]:
    """Crea un ChunkPlan separato per ogni modulo rilevato."""
    from .chunker import create_chunks as _create_chunks, ChunkPlan as _CP, Chunk

    by_module = scan_result.files_by_module()
    module_plans: dict[str, ChunkPlan] = {}

    budget_chars = config.tokens_to_chars(config.chunk_budget)

    for module_name in sorted(by_module.keys()):
        files = by_module[module_name]
        priority_order = {"alta": 0, "media": 1, "bassa": 2}
        files.sort(key=lambda f: (priority_order.get(f.priority, 2), f.path))

        plan = ChunkPlan()
        current_chunk = Chunk(module=module_name)

        for file in files:
            file_chars = len(file.content)

            if file_chars > budget_chars:
                if current_chunk.files:
                    plan.chunks.append(current_chunk)
                    current_chunk = Chunk(module=module_name)
                big_chunk = Chunk(module=module_name)
                big_chunk.add_file(file)
                plan.chunks.append(big_chunk)
                continue

            if current_chunk.total_chars + file_chars > budget_chars:
                plan.chunks.append(current_chunk)
                current_chunk = Chunk(module=module_name)

            current_chunk.add_file(file)

        if current_chunk.files:
            plan.chunks.append(current_chunk)

        if plan.chunks:
            module_plans[module_name] = plan

    return module_plans


def _estimate_hybrid_cost(module_plans: dict[str, ChunkPlan], analysis_tokens: int = 0) -> float:
    """Stima il costo della generazione ibrida.
    
    Stime basate su osservazioni reali:
    - Analisi chunk: ~3.5K token output (max_output_tokens=4096)
    - Doc func/tech: ~8K token output ciascuno (max_output_tokens=8192)
    - Summary: ~1.5K token output (max_output_tokens=2048)
    - Ogni chiamata API invia anche il testo dell'analisi statica come contesto
    - system prompt: ~500 token per chiamata
    """
    from .config import COST_INPUT_PER_M, COST_OUTPUT_PER_M

    total_input = 0
    total_output = 0

    # Overhead fisso per chiamata: system prompt + template prompt
    call_overhead = 500  # system prompt incluso da Anthropic

    # Analisi statica inviata come contesto in chunk analysis + doc calls
    # Se non fornita, stima conservativa basata su dimensione progetto
    static_tokens = analysis_tokens if analysis_tokens > 0 else 5000

    total_chunks_all = sum(p.total_chunks for p in module_plans.values())

    for plan in module_plans.values():
        n_chunks = plan.total_chunks

        # Fase 1: analisi chunk — Claude usa ~95% di max_output_tokens=4096
        phase1_input = plan.total_input_tokens + (n_chunks * (static_tokens + 3000 + call_overhead))
        phase1_output = n_chunks * 4000

        # Fase 2-3: func + tech doc — input = analisi troncate + static_analysis + prompt
        synthesis_analyses = min(phase1_output, 100_000)
        synthesis_input_per_doc = synthesis_analyses + static_tokens + 3000 + call_overhead
        phase23_output = 32000  # 16K per doc (max_output_tokens=16384)

        # Fase summary — input = analisi troncate + prompt (no static)
        summary_input = min(phase1_output, 100_000) + 3000 + call_overhead
        summary_output = 2000  # max_output_tokens=2048

        total_input += phase1_input + (synthesis_input_per_doc * 2) + summary_input
        total_output += phase1_output + phase23_output + summary_output

    # Doc architettura sistema — riceve tutti i summary + static + prompt
    arch_input = len(module_plans) * 1500 + static_tokens + 3000 + call_overhead
    total_input += arch_input
    total_output += 16000  # max_output_tokens=16384

    return (
        (total_input / 1_000_000) * COST_INPUT_PER_M
        + (total_output / 1_000_000) * COST_OUTPUT_PER_M
    )


def _print_hybrid_plan(module_plans: dict[str, ChunkPlan], analysis_tokens: int = 0) -> None:
    """Stampa il piano per la generazione ibrida."""
    console.print(f"\n[bold]📦 Piano generazione ibrida[/bold]")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Microservizio")
    table.add_column("Chunk", justify="right")
    table.add_column("File", justify="right")
    table.add_column("Token est.", justify="right")
    table.add_column("Documenti")

    for name, plan in sorted(module_plans.items()):
        table.add_row(
            name,
            str(plan.total_chunks),
            str(plan.total_files),
            f"{plan.total_input_tokens:,}",
            "Funzionale + Tecnica",
        )

    console.print(table)

    total_chunks = sum(p.total_chunks for p in module_plans.values())
    total_files = sum(p.total_files for p in module_plans.values())
    total_tokens = sum(p.total_input_tokens for p in module_plans.values())
    estimated_cost = _estimate_hybrid_cost(module_plans, analysis_tokens)

    console.print(f"\n  Microservizi: {len(module_plans)}")
    console.print(f"  Chunk totali: {total_chunks}")
    console.print(f"  File totali: {total_files}")
    console.print(f"  Token input stimati: {total_tokens:,}")
    console.print(f"  Documenti da generare: {len(module_plans) * 2} + 1 architettura sistema")
    console.print(f"  [bold]Costo stimato: ${estimated_cost:.4f}[/bold]")


def _ask_generation_mode(
    scan_result: ScanResult,
    chunk_plan: ChunkPlan,
    module_plans: dict[str, ChunkPlan],
    analysis_tokens: int = 0,
) -> str:
    """Chiede all'utente come procedere per un progetto multi-microservizio.
    
    Ritorna: 'hybrid', 'unified', o 'cancel'.
    """
    n_modules = len(module_plans)
    hybrid_cost = _estimate_hybrid_cost(module_plans, analysis_tokens)
    unified_cost = chunk_plan.estimate_total_cost(analysis_tokens)

    console.print(Panel(
        f"[bold yellow]Progetto multi-microservizio rilevato![/bold yellow]\n\n"
        f"Sono stati rilevati [bold]{n_modules} microservizi[/bold] "
        f"con {chunk_plan.total_chunks} chunk totali.\n"
        f"Puoi scegliere come generare la documentazione:",
        border_style="yellow",
    ))

    console.print(
        f"\n  [bold cyan][1][/bold cyan] Per microservizio + Architettura di sistema "
        f"[green](consigliato)[/green]\n"
        f"      → {n_modules * 2} documenti (funzionale + tecnica per servizio)\n"
        f"      → 1 documento architettura di sistema (integrazioni, flussi, diagrammi)\n"
        f"      → Costo stimato: [bold]${hybrid_cost:.4f}[/bold]"
    )
    console.print(
        f"\n  [bold cyan][2][/bold cyan] Tutto insieme (modalità classica)\n"
        f"      → 2 documenti (funzionale + tecnica unici)\n"
        f"      → Costo stimato: [bold]${unified_cost:.4f}[/bold]"
    )
    console.print(
        f"\n  [bold cyan][3][/bold cyan] Annulla\n"
    )

    while True:
        choice = console.input("[bold]Scelta (1/2/3): [/bold]").strip()
        if choice == "1":
            return "hybrid"
        elif choice == "2":
            return "unified"
        elif choice == "3":
            return "cancel"
        else:
            console.print("[red]Scelta non valida. Inserisci 1, 2 o 3.[/red]")


def _save_static_outputs(
    result: ScanResult,
    analysis: ProjectAnalysis,
    output_dir: str,
) -> None:
    """Salva file di analisi statica e struttura progetto."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Struttura progetto
    structure_path = out_path / "struttura_progetto.txt"
    lines: list[str] = []
    by_module = result.files_by_module()
    for module in sorted(by_module.keys()):
        lines.append(f"[{module}]")
        for f in sorted(by_module[module], key=lambda x: x.path):
            lines.append(f"  {f.path}  ({f.category}, {f.priority})")
        lines.append("")
    structure_path.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"  [green]✓[/green] {structure_path.name}")

    # Analisi statica
    analysis_path = out_path / "analisi_statica.md"
    analysis_path.write_text(analysis.summary_text(), encoding="utf-8")
    console.print(f"  [green]✓[/green] {analysis_path.name}")


def _export_prompts_unified(
    chunk_plan: ChunkPlan,
    analysis: ProjectAnalysis,
    config: DocGenConfig,
) -> list[str]:
    """Esporta i prompt per la modalità unificata.

    Genera un file per ogni fase:
    - 01_ANALISI_CHUNK_N.md (uno per chunk)
    - 02_SPECIFICA_FUNZIONALE.md
    - 03_SPECIFICA_TECNICA.md

    Ritorna la lista di file generati.
    """
    static_text = analysis.summary_text()
    prompts_dir = Path(config.output_dir) / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    # System prompt
    sys_path = prompts_dir / "00_SYSTEM_PROMPT.md"
    sys_path.write_text(
        "# System Prompt\n\n"
        "Invia questo come **system prompt** o incollalo all'inizio della conversazione.\n\n"
        "---\n\n" + SYSTEM_PROMPT,
        encoding="utf-8",
    )
    generated.append(str(sys_path))
    console.print(f"  [green]✓[/green] {sys_path.name}")

    # Prompt di analisi per ogni chunk
    for i, chunk in enumerate(chunk_plan.chunks, 1):
        prompt = ANALYZE_CHUNK.format(
            project_name=config.project_name,
            static_analysis=static_text,
            chunk_content=chunk.to_text(),
        )
        fname = f"01_ANALISI_CHUNK_{i:02d}_{chunk.module}.md"
        fpath = prompts_dir / fname
        fpath.write_text(
            f"# Prompt Analisi — Chunk {i}: {chunk.module}\n\n"
            f"Token stimati: ~{config.chars_to_tokens(len(prompt)):,}\n\n"
            f"---\n\n{prompt}",
            encoding="utf-8",
        )
        generated.append(str(fpath))
        console.print(f"  [green]✓[/green] {fname}")

    # Placeholder: i prompt di sintesi richiedono le risposte dei chunk
    placeholder = (
        "[INSERISCI QUI LE RISPOSTE OTTENUTE DAI PROMPT DI ANALISI CHUNK]\n\n"
        "Copia le risposte che hai ottenuto inviando i prompt 01_ANALISI_CHUNK_*.md "
        "e incollale al posto di questo placeholder."
    )

    # Prompt doc funzionale
    func_prompt = FUNCTIONAL_DOC.format(
        project_name=config.project_name,
        static_analysis=static_text,
        module_analyses=placeholder,
    )
    func_path = prompts_dir / "02_SPECIFICA_FUNZIONALE.md"
    func_path.write_text(
        f"# Prompt Specifica Funzionale — {config.project_name}\n\n"
        f"**PREREQUISITO**: Prima manda i prompt `01_ANALISI_CHUNK_*.md` e raccogli le risposte.\n"
        f"Poi sostituisci il placeholder `[INSERISCI QUI...]` con le risposte concatenate.\n\n"
        f"---\n\n{func_prompt}",
        encoding="utf-8",
    )
    generated.append(str(func_path))
    console.print(f"  [green]✓[/green] {func_path.name}")

    # Prompt doc tecnica
    tech_prompt = TECHNICAL_DOC.format(
        project_name=config.project_name,
        static_analysis=static_text,
        module_analyses=placeholder,
    )
    tech_path = prompts_dir / "03_SPECIFICA_TECNICA.md"
    tech_path.write_text(
        f"# Prompt Specifica Tecnica — {config.project_name}\n\n"
        f"**PREREQUISITO**: Stesse risposte dei chunk usate per la specifica funzionale.\n\n"
        f"---\n\n{tech_prompt}",
        encoding="utf-8",
    )
    generated.append(str(tech_path))
    console.print(f"  [green]✓[/green] {tech_path.name}")

    return generated


def _export_prompts_hybrid(
    module_plans: dict[str, ChunkPlan],
    analysis: ProjectAnalysis,
    config: DocGenConfig,
) -> list[str]:
    """Esporta i prompt per la modalità ibrida (per-microservizio).

    Struttura output:
    prompts/
    ├── 00_SYSTEM_PROMPT.md
    ├── administration-api/
    │   ├── 01_ANALISI_CHUNK_01.md
    │   ├── 02_SPECIFICA_FUNZIONALE.md
    │   ├── 03_SPECIFICA_TECNICA.md
    │   └── 04_RIEPILOGO_SERVIZIO.md
    ├── avvocati-api/
    │   └── ...
    └── ARCHITETTURA_SISTEMA.md
    """
    static_text = analysis.summary_text()
    synthesis_budget_chars = config.tokens_to_chars(100_000)
    prompts_dir = Path(config.output_dir) / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    # System prompt
    sys_path = prompts_dir / "00_SYSTEM_PROMPT.md"
    sys_path.write_text(
        "# System Prompt\n\n"
        "Invia questo come **system prompt** o incollalo all'inizio di ogni conversazione.\n\n"
        "---\n\n" + SYSTEM_PROMPT,
        encoding="utf-8",
    )
    generated.append(str(sys_path))
    console.print(f"  [green]✓[/green] 00_SYSTEM_PROMPT.md")

    service_summary_placeholder_parts: list[str] = []

    for mod_name, chunk_plan in sorted(module_plans.items()):
        mod_dir = prompts_dir / mod_name
        mod_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"\n  [bold yellow]{mod_name}[/bold yellow]")

        # Analisi chunk
        for i, chunk in enumerate(chunk_plan.chunks, 1):
            prompt = ANALYZE_CHUNK.format(
                project_name=config.project_name,
                static_analysis=static_text,
                chunk_content=chunk.to_text(),
            )
            fname = f"01_ANALISI_CHUNK_{i:02d}_{chunk.module}.md"
            fpath = mod_dir / fname
            fpath.write_text(
                f"# Prompt Analisi — {mod_name} — Chunk {i}\n\n"
                f"Token stimati: ~{config.chars_to_tokens(len(prompt)):,}\n\n"
                f"---\n\n{prompt}",
                encoding="utf-8",
            )
            generated.append(str(fpath))
            console.print(f"    [green]✓[/green] {fname}")

        placeholder = (
            "[INSERISCI QUI LE RISPOSTE DEI PROMPT 01_ANALISI_CHUNK_*.md "
            f"PER {mod_name}]"
        )

        # Doc funzionale
        func_prompt = FUNCTIONAL_DOC.format(
            project_name=f"{config.project_name} — {mod_name}",
            static_analysis=static_text,
            module_analyses=placeholder,
        )
        func_path = mod_dir / "02_SPECIFICA_FUNZIONALE.md"
        func_path.write_text(
            f"# Prompt Specifica Funzionale — {mod_name}\n\n"
            f"**PREREQUISITO**: Prima manda i prompt `01_ANALISI_CHUNK_*.md` di questa cartella "
            f"e sostituisci il placeholder con le risposte.\n\n"
            f"---\n\n{func_prompt}",
            encoding="utf-8",
        )
        generated.append(str(func_path))
        console.print(f"    [green]✓[/green] 02_SPECIFICA_FUNZIONALE.md")

        # Doc tecnica
        tech_prompt = TECHNICAL_DOC.format(
            project_name=f"{config.project_name} — {mod_name}",
            static_analysis=static_text,
            module_analyses=placeholder,
        )
        tech_path = mod_dir / "03_SPECIFICA_TECNICA.md"
        tech_path.write_text(
            f"# Prompt Specifica Tecnica — {mod_name}\n\n"
            f"**PREREQUISITO**: Stesse risposte chunk usate per la specifica funzionale.\n\n"
            f"---\n\n{tech_prompt}",
            encoding="utf-8",
        )
        generated.append(str(tech_path))
        console.print(f"    [green]✓[/green] 03_SPECIFICA_TECNICA.md")

        # Riepilogo servizio (per architettura)
        summary_prompt = SERVICE_SUMMARY.format(
            service_name=mod_name,
            module_analyses=placeholder,
        )
        summary_path = mod_dir / "04_RIEPILOGO_SERVIZIO.md"
        summary_path.write_text(
            f"# Prompt Riepilogo Servizio — {mod_name}\n\n"
            f"**PREREQUISITO**: Stesse risposte chunk.\n"
            f"Questo riepilogo serve come input per il prompt di architettura di sistema.\n\n"
            f"---\n\n{summary_prompt}",
            encoding="utf-8",
        )
        generated.append(str(summary_path))
        console.print(f"    [green]✓[/green] 04_RIEPILOGO_SERVIZIO.md")

        service_summary_placeholder_parts.append(
            f"### {mod_name}\n\n"
            f"[INSERISCI QUI LA RISPOSTA DEL PROMPT 04_RIEPILOGO_SERVIZIO.md DI {mod_name}]"
        )

    # Architettura di sistema
    all_summaries_placeholder = "\n\n---\n\n".join(service_summary_placeholder_parts)
    arch_prompt = SYSTEM_ARCHITECTURE_DOC.format(
        project_name=config.project_name,
        static_analysis=static_text,
        service_summaries=all_summaries_placeholder,
    )
    arch_path = prompts_dir / "ARCHITETTURA_SISTEMA.md"
    arch_path.write_text(
        f"# Prompt Architettura di Sistema — {config.project_name}\n\n"
        f"**PREREQUISITO**: Prima genera i riepiloghi di tutti i microservizi "
        f"(prompt `04_RIEPILOGO_SERVIZIO.md` in ogni cartella).\n"
        f"Poi sostituisci ogni placeholder con la risposta ottenuta.\n\n"
        f"---\n\n{arch_prompt}",
        encoding="utf-8",
    )
    generated.append(str(arch_path))
    console.print(f"\n  [green]✓[/green] ARCHITETTURA_SISTEMA.md")

    return generated


# ═══════════════════════════════════════════════════════════════════════════════
# Agent Export
# ═══════════════════════════════════════════════════════════════════════════════


def _build_project_tree(scan_result: ScanResult) -> str:
    """Costruisce un albero testuale della struttura del progetto."""
    lines: list[str] = []
    by_module = scan_result.files_by_module()
    for module in sorted(by_module.keys()):
        lines.append(f"📁 {module}/")
        for f in sorted(by_module[module], key=lambda x: x.path):
            marker = "⚠️" if f.category == "business_critical" else " "
            lines.append(f"  {marker} {f.path}  [{f.category}] ({f.priority})")
    return "\n".join(lines)


def _build_detection_reason(file: 'ScannedFile') -> str:
    """Restituisce la ragione per cui un file è stato classificato come business_critical."""
    if file.category != "business_critical":
        return ""
    from .scanner import BUSINESS_CRITICAL_NAME_PATTERNS, _BUSINESS_CRITICAL_CONTENT_RE
    reasons: list[str] = []
    basename_no_ext = os.path.splitext(os.path.basename(file.path))[0].lower()
    for kw in BUSINESS_CRITICAL_NAME_PATTERNS:
        if kw in basename_no_ext or kw in file.path.lower():
            reasons.append(f"nome contiene '{kw}'")
            break
    if file.content:
        match = _BUSINESS_CRITICAL_CONTENT_RE.search(file.content)
        if match:
            reasons.append(f"contiene {match.group(0)}")
    return "; ".join(reasons) if reasons else "pattern business-critical"


# ── Urgency grouping (P7) ───────────────────────────────────────────────

# Categorie raggruppate per urgenza visiva
_URGENCY_RED = {"business_critical", "controller", "service"}
_URGENCY_YELLOW = {"entity", "repository", "config", "dto", "dbcontext", "angular_service", "angular_component", "angular_module"}
# Tutto il resto → ⚪


def _file_urgency(f: 'ScannedFile') -> str:
    """Restituisce l'emoji urgenza per un file."""
    if f.category in _URGENCY_RED:
        return "🔴"
    if f.category in _URGENCY_YELLOW:
        return "🟡"
    return "⚪"


def _append_urgency_file_list(lines: list[str], files: list['ScannedFile']) -> None:
    """Aggiunge al buffer la lista file raggruppata per urgenza (P7)."""
    red_files = [f for f in files if f.category in _URGENCY_RED]
    yellow_files = [f for f in files if f.category in _URGENCY_YELLOW]
    white_files = [f for f in files if f.category not in _URGENCY_RED and f.category not in _URGENCY_YELLOW]

    if red_files:
        lines.append("### 🔴 Obbligatori — leggere SEMPRE\n")
        lines.append("Contengono la logica di business principale, controller e servizi critici.\n")
        for f in sorted(red_files, key=lambda x: (x.category, x.path)):
            extra = ""
            if f.category == "business_critical":
                reason = _build_detection_reason(f)
                extra = f" → {reason}" if reason else ""
            lines.append(f"- `{f.path}` [{f.category}]{extra}")
        lines.append("")

    if yellow_files:
        lines.append("### 🟡 Importanti — leggere se necessario\n")
        lines.append("Entità, repository, configurazioni e DTO di supporto.\n")
        for f in sorted(yellow_files, key=lambda x: (x.category, x.path)):
            lines.append(f"- `{f.path}` [{f.category}]")
        lines.append("")

    if white_files:
        lines.append("### ⚪ Supporto — leggere solo se serve contesto aggiuntivo\n")
        lines.append("Test, utility, stili e file di supporto.\n")
        for f in sorted(white_files, key=lambda x: (x.category, x.path)):
            lines.append(f"- `{f.path}` [{f.category}]")
        lines.append("")


# ── Per-microservice context generation (P6) ─────────────────────────────

def _generate_module_context_md(
    module_name: str,
    module_files: list['ScannedFile'],
    analysis: ProjectAnalysis,
    config: DocGenConfig,
) -> str:
    """Genera il contesto per un singolo microservizio."""
    lines: list[str] = []

    lines.append(f"# Microservizio: {module_name}")
    lines.append(f"\n> Progetto: {config.project_name}")
    lines.append(f"> Generato da DocGen il {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Statistiche modulo
    lines.append("## Statistiche\n")
    lines.append(f"- **File**: {len(module_files)}")
    ext_counts: dict[str, int] = {}
    for f in module_files:
        ext_counts[f.extension] = ext_counts.get(f.extension, 0) + 1
    lang_list = ", ".join(f"{ext} ({c})" for ext, c in sorted(ext_counts.items(), key=lambda x: -x[1])[:10])
    lines.append(f"- **Linguaggi**: {lang_list}")
    lines.append("")

    # Analisi statica filtrata per questo modulo
    module_analysis = analysis.summary_text_for_module(module_name)
    if module_analysis:
        lines.append(module_analysis)
        lines.append("")

    # File per urgenza (P7)
    lines.append("## File del microservizio\n")
    _append_urgency_file_list(lines, module_files)

    # Istruzioni specifiche per questo modulo
    lines.append("---\n")
    lines.append("## Documenti da generare\n")
    lines.append(f"Per questo microservizio genera:\n")
    lines.append(f"1. `{module_name}/specifica_funzionale.md`")
    lines.append(f"2. `{module_name}/specifica_tecnica.md`\n")
    lines.append("Leggi i file 🔴 obbligatoriamente. Per i file 🟡, leggili se servono dettagli su entità o configurazioni. "
                  "I file ⚪ solo se hai bisogno di contesto aggiuntivo.\n")

    return "\n".join(lines)


def _generate_instructions_md_docs(
    config: DocGenConfig,
    module_names: list[str],
) -> str:
    """Genera le istruzioni generali per l'agente (linguaggio naturale, no placeholder Python)."""
    lines: list[str] = []

    lines.append("# Istruzioni per la generazione della documentazione")
    lines.append(f"\n> Progetto: {config.project_name}\n")

    lines.append("## Ruolo\n")
    lines.append(
        "Sei un agente AI con accesso al filesystem del progetto. "
        "Hai a disposizione i file di contesto per ogni microservizio e puoi leggere qualsiasi file "
        "direttamente dalla workspace.\n\n"
        "NON ti serve che il codice sia incollato nei prompt — leggi i file dal filesystem quando necessario.\n"
    )

    lines.append("## Piano di lavoro\n")
    lines.append("Procedi nell'ordine seguente:\n")

    for i, mod_name in enumerate(module_names, 1):
        lines.append(
            f"{i}. Leggi il file `docgen_context_{mod_name}.md`, "
            f"poi genera `{mod_name}/specifica_funzionale.md` e `{mod_name}/specifica_tecnica.md`."
        )

    n = len(module_names) + 1
    other_modules_list = ", ".join(f"`docgen_context_{m}.md`" for m in module_names)
    lines.append(
        f"{n}. **Revisione cross-service**: dopo aver generato la bozza di tutti i microservizi, "
        f"rileggi i context degli altri moduli ({other_modules_list}) e verifica se emergono informazioni "
        f"che integrano o correggono i documenti già scritti. "
        f"In particolare controlla:\n"
        f"   - Dipendenze tra servizi (un servizio chiama API di un altro)\n"
        f"   - Entità condivise o ID referenziati cross-service\n"
        f"   - Flussi operativi che coinvolgono più microservizi in sequenza\n"
        f"   Se trovi integrazioni rilevanti, aggiorna le sezioni '7. Integrazioni' "
        f"e '4. Flussi operativi' dei documenti già generati prima di procedere.\n"
    )

    n += 1
    lines.append(
        f"{n}. Dopo la revisione, genera i documenti d'insieme:\n"
        f"   - `architettura_sistema.md` — come i microservizi collaborano, API interne, flussi principali\n"
        f"   - `specifica_funzionale_completa.md` — visione funzionale end-to-end del sistema\n"
        f"   - `specifica_tecnica_completa.md` — visione tecnica end-to-end del sistema\n"
    )

    lines.append("## Regole di lettura file\n")
    lines.append("- File 🔴 (obbligatori): leggili SEMPRE prima di generare il documento.")
    lines.append("- File 🟡 (importanti): leggili se servono dettagli su entità, repository o configurazioni.")
    lines.append("- File ⚪ (supporto): leggili solo se hai bisogno di contesto aggiuntivo.")
    lines.append("- Per i file classificati come business_critical, leggi SEMPRE il contenuto completo.\n")

    lines.append("## Formato output\n")
    lines.append("Tutti i documenti devono essere in Markdown. Scrivi in italiano.\n")

    # Template
    lines.append("---\n")
    lines.append("## Template: Specifica Funzionale\n")
    lines.append("Segui ESATTAMENTE questa struttura per il documento funzionale:\n")
    func_instructions = FUNCTIONAL_DOC.split("## Istruzioni")[1] if "## Istruzioni" in FUNCTIONAL_DOC else FUNCTIONAL_DOC
    lines.append(func_instructions.strip())
    lines.append("")

    lines.append("---\n")
    lines.append("## Template: Specifica Tecnica\n")
    lines.append("Segui ESATTAMENTE questa struttura per il documento tecnico:\n")
    tech_instructions = TECHNICAL_DOC.split("## Istruzioni")[1] if "## Istruzioni" in TECHNICAL_DOC else TECHNICAL_DOC
    lines.append(tech_instructions.strip())
    lines.append("")

    lines.append("---\n")
    lines.append("## Template: Architettura di Sistema\n")
    lines.append("Segui ESATTAMENTE questa struttura per il documento di architettura:\n")
    arch_instructions = SYSTEM_ARCHITECTURE_DOC.split("## Istruzioni")[1] if "## Istruzioni" in SYSTEM_ARCHITECTURE_DOC else SYSTEM_ARCHITECTURE_DOC
    lines.append(arch_instructions.strip())
    lines.append("")

    lines.append("---\n")
    lines.append(f"## Output\n")
    lines.append(f"Salva tutti i documenti generati in: `{config.output_dir}`\n")

    lines.append("---\n")
    lines.append("## Post-generazione: conversione DOCX e pulizia\n")
    lines.append(
        "Dopo aver generato TUTTI i documenti .md, esegui questi comandi nel terminale:\n\n"
        "### 1. Conversione in formato Word (.docx) con template aziendale\n\n"
        "```bash\n"
    )
    lines.append(f"python -m docgen --render {config.output_dir}/*.md"
                  f" --meta PROGETTO=\"{config.project_name}\"\n")
    lines.append(
        "```\n\n"
        "Puoi personalizzare i metadati della copertina aggiungendo parametri `--meta`:\n"
        "- `CLIENTE=\"Nome Cliente\"`\n"
        "- `PROGETTO=\"Nome Progetto\"`\n"
        "- `INTESTAZIONE_ENTE=\"Nome Ente\"`\n"
        "- `REDATTO_DA=\"Nome Autore\"`\n"
        "- `VERSIONE=\"1.0\"`\n\n"
        "### 2. Pulizia file temporanei\n\n"
        "```bash\n"
    )
    lines.append(f"python -m docgen --cleanup {config.output_dir}\n")
    lines.append(
        "```\n\n"
        "Questo rimuove i file di contesto (analisi_statica.md, docgen_context_*.md, "
        "docgen_files.json, docgen_index.md, docgen_instructions.md, struttura_progetto.txt) "
        "lasciando solo i documenti finali .md e .docx.\n"
    )

    return "\n".join(lines)


# ── Generatori modalità TESTS ─────────────────────────────────────────────────

def _generate_instructions_md_tests(
    config: DocGenConfig,
    module_names: list[str],
    test_analysis: 'TestStaticAnalysis | None',
) -> str:
    """Genera docgen_instructions.md per la modalità tests (multi-microservizio)."""
    from .analyzer import TestStaticAnalysis as _TSA
    lines: list[str] = []

    lines.append("# Istruzioni per la generazione dell'analisi di test")
    lines.append(f"\n> Progetto: {config.project_name}")
    lines.append(f"> Modalità: tests\n")

    lines.append("## Ruolo\n")
    lines.append(
        "Sei un QA engineer senior con accesso al filesystem del progetto. "
        "Hai a disposizione i file di contesto per ogni microservizio (analisi statica, "
        "firme di metodi, validazioni, autorizzazioni, enumerazioni, eccezioni, chiamate esterne) "
        "e puoi leggere qualsiasi file direttamente dalla workspace.\n\n"
        "**NON ti serve che il codice sia incollato nei prompt** — leggi i file dal filesystem quando necessario.\n"
    )

    lines.append("## Piano di lavoro\n")
    lines.append("Procedi nell'ordine seguente:\n")

    for i, mod_name in enumerate(module_names, 1):
        lines.append(
            f"{i}. Leggi il file `docgen_context_{mod_name}.md`, "
            f"poi genera `{mod_name}/analisi_test.md`."
        )

    n = len(module_names) + 1
    lines.append(
        f"{n}. Dopo aver completato tutti i microservizi, genera il documento d'insieme:\n"
        f"   - `analisi_test_sistema.md` — panoramica sistema, aree di rischio "
        f"trasversali, casi di integrazione cross-microservizio\n"
    )

    lines.append("## Regole di lettura file\n")
    lines.append("- File 🔴 (obbligatori): leggili SEMPRE prima di generare il documento.")
    lines.append("- File 🟡 (importanti): leggili se servono dettagli su entità, repository o configurazioni.")
    lines.append("- File ⚪ (supporto): leggili solo se hai bisogno di contesto aggiuntivo.")
    lines.append("- Per i file classificati come business_critical, leggi SEMPRE il contenuto completo.\n")

    lines.append("## Formato output\n")
    lines.append(
        "Tutti i documenti devono essere in Markdown. Scrivi in italiano. "
        "Usa tabelle per i casi di test con ID progressivo (TC-F-001, TC-T-001, ecc.).\n"
    )

    lines.append("---\n")
    lines.append("## Template: Documento di Analisi Test\n")
    lines.append("Segui ESATTAMENTE questa struttura per ogni documento di analisi test:\n")
    lines.append(TEST_DOCUMENT_TEMPLATE.strip())
    lines.append("")

    lines.append("---\n")
    lines.append(f"## Output\n")
    lines.append(f"Salva tutti i documenti generati in: `{config.output_dir}`\n")

    lines.append("---\n")
    lines.append("## Post-generazione: pulizia\n")
    lines.append(
        "Dopo aver generato TUTTI i documenti .md, esegui il cleanup:\n\n"
        "```bash\n"
    )
    lines.append(f"python -m docgen --cleanup {config.output_dir}\n")
    lines.append("```\n")

    return "\n".join(lines)


def _generate_module_context_md_tests(
    module_name: str,
    module_files: list['ScannedFile'],
    analysis: ProjectAnalysis,
    test_analysis: 'TestStaticAnalysis | None',
    config: DocGenConfig,
) -> str:
    """Genera il contesto di test per un singolo microservizio."""
    lines: list[str] = []

    lines.append(f"# Analisi Test — Microservizio: {module_name}")
    lines.append(f"\n> Progetto: {config.project_name}")
    lines.append(f"> Modalità: tests")
    lines.append(f"> Generato da DocGen il {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # Statistiche modulo
    lines.append("## Statistiche\n")
    lines.append(f"- **File**: {len(module_files)}")
    ext_counts: dict[str, int] = {}
    for f in module_files:
        ext_counts[f.extension] = ext_counts.get(f.extension, 0) + 1
    lang_list = ", ".join(f"{ext} ({c})" for ext, c in sorted(ext_counts.items(), key=lambda x: -x[1])[:10])
    lines.append(f"- **Linguaggi**: {lang_list}")
    lines.append("")

    # Analisi statica standard filtrata per modulo
    module_analysis_text = analysis.summary_text_for_module(module_name)
    if module_analysis_text:
        lines.append(module_analysis_text)
        lines.append("")

    # Analisi estesa per test filtrata per modulo
    if test_analysis:
        test_summary = test_analysis.summary_text_for_module(module_name)
        if test_summary:
            lines.append(test_summary)
            lines.append("")

    # File per urgenza
    lines.append("## File del microservizio\n")
    _append_urgency_file_list(lines, module_files)

    lines.append("---\n")
    lines.append("## Documento da generare\n")
    lines.append(f"Per questo microservizio genera:\n")
    lines.append(f"1. `{module_name}/analisi_test.md`\n")
    lines.append(
        "Leggi i file 🔴 obbligatoriamente. Usa l'analisi statica estesa "
        "(firme, validazioni, sicurezza, eccezioni) per identificare i casi di test.\n"
    )

    return "\n".join(lines)


def _generate_context_md_tests(
    scan_result: ScanResult,
    analysis: ProjectAnalysis,
    test_analysis: 'TestStaticAnalysis | None',
    config: DocGenConfig,
    is_hybrid: bool,
    module_plans: 'dict[str, ChunkPlan] | None',
) -> str:
    """Genera docgen_context.md per la modalità tests (progetto singolo)."""
    lines: list[str] = []

    lines.append(f"# Analisi Test — Progetto: {config.project_name}")
    lines.append(f"\n> Modalità: tests")
    lines.append(f"> Generato da DocGen il {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> Progetto: `{config.project_path}`\n")

    # Struttura directory
    lines.append("## Struttura directory\n")
    lines.append("```")
    lines.append(_build_project_tree(scan_result))
    lines.append("```\n")

    # Statistiche
    lines.append("## Statistiche\n")
    ext_counts = scan_result.top_extensions(15)
    lang_list = ", ".join(f"{ext} ({count})" for ext, count in ext_counts)
    lines.append(f"- **File totali**: {scan_result.total_files}")
    lines.append(f"- **Moduli rilevati**: {', '.join(scan_result.modules)}")
    lines.append(f"- **Linguaggi**: {lang_list}")
    if is_hybrid and module_plans:
        lines.append(f"- **Microservizi**: {len(module_plans)}")
    lines.append("")

    # Analisi statica standard
    lines.append(analysis.summary_text())
    lines.append("")

    # Analisi estesa per test
    if test_analysis:
        test_text = test_analysis.summary_text()
        if test_text:
            lines.append(test_text)
            lines.append("")

    # File per urgenza
    lines.append("## File classificati per urgenza\n")
    _append_urgency_file_list(lines, scan_result.files)

    # Istruzioni per l'agente
    lines.append("---\n")
    lines.append("## Istruzioni per la generazione dell'analisi di test\n")
    lines.append(
        "Sei un QA engineer senior con accesso al filesystem del progetto. "
        "Hai a disposizione l'analisi strutturale sopra e puoi leggere qualsiasi file "
        "direttamente dalla workspace.\n\n"
        "**NON ti serve che il codice sia incollato nei prompt** — leggi i file dal filesystem quando necessario.\n"
    )

    lines.append("### Piano di lavoro\n")
    lines.append("Devi generare il seguente documento Markdown:\n")
    lines.append("1. `analisi_test.md` — documento completo di analisi test\n")
    lines.append("### Procedura:\n")
    lines.append("1. Leggi i file 🔴 (obbligatori) e 🟡 (se necessario) dalla lista sopra")
    lines.append("2. Usa l'analisi statica estesa (firme, validazioni, sicurezza, eccezioni) per identificare i casi di test")
    lines.append("3. Genera il documento seguendo il template sotto\n")

    lines.append("---\n")
    lines.append("## Template: Documento di Analisi Test\n")
    lines.append("Segui ESATTAMENTE questa struttura:\n")
    lines.append(TEST_DOCUMENT_TEMPLATE.strip())
    lines.append("")

    lines.append("---\n")
    lines.append(f"## Output\n")
    lines.append(f"Salva il documento generato in: `{config.output_dir}`\n")

    lines.append("---\n")
    lines.append("## Post-generazione: pulizia\n")
    lines.append("```bash\n")
    lines.append(f"python -m docgen --cleanup {config.output_dir}\n")
    lines.append("```\n")

    return "\n".join(lines)


def _generate_index_md(
    config: DocGenConfig,
    module_names: list[str],
    is_hybrid: bool,
) -> str:
    """Genera l'indice dei file di export."""
    lines: list[str] = []

    lines.append(f"# DocGen Agent Export — {config.project_name}")
    lines.append(f"\n> Generato il {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    lines.append("## File generati\n")

    if is_hybrid and module_names:
        lines.append("| File | Descrizione |")
        lines.append("|------|-------------|")
        lines.append("| `docgen_instructions.md` | Istruzioni generali + template documenti |")
        for mod in module_names:
            lines.append(f"| `docgen_context_{mod}.md` | Contesto e file del microservizio {mod} |")
        lines.append("| `docgen_files.json` | Dati machine-readable (tutti i file) |")
        lines.append("| `docgen_index.md` | Questo file |")
    else:
        lines.append("| File | Descrizione |")
        lines.append("|------|-------------|")
        lines.append("| `docgen_context.md` | Contesto completo + istruzioni + template |")
        lines.append("| `docgen_files.json` | Dati machine-readable |")
        lines.append("| `docgen_index.md` | Questo file |")

    lines.append("")
    lines.append("## Come usare\n")
    if is_hybrid and module_names:
        lines.append(
            "1. Passa `docgen_instructions.md` all'agente come prompt iniziale.\n"
            "2. L'agente leggerà i file `docgen_context_*.md` uno alla volta per ogni microservizio.\n"
            "3. Per ogni microservizio genererà specifica funzionale e tecnica.\n"
            "4. Infine genererà i documenti d'insieme (architettura, funzionale completa, tecnica completa).\n"
        )
    else:
        lines.append(
            "Passa `docgen_context.md` come prompt all'agente (Copilot, Kilo Code, Claude Code).\n"
            "L'agente leggerà i file dal workspace e genererà la documentazione.\n"
        )

    return "\n".join(lines)


def _generate_context_md(
    scan_result: ScanResult,
    analysis: ProjectAnalysis,
    config: DocGenConfig,
    is_hybrid: bool,
    module_plans: dict[str, ChunkPlan] | None,
) -> str:
    """Genera il contenuto di docgen_context.md per l'agente."""
    lines: list[str] = []

    lines.append(f"# Analisi strutturale del progetto: {config.project_name}")
    lines.append(f"\n> Generato da DocGen il {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"> Progetto: `{config.project_path}`\n")

    # Struttura directory
    lines.append("## Struttura directory\n")
    lines.append("```")
    lines.append(_build_project_tree(scan_result))
    lines.append("```\n")

    # Statistiche
    lines.append("## Statistiche\n")
    ext_counts = scan_result.top_extensions(15)
    lang_list = ", ".join(f"{ext} ({count})" for ext, count in ext_counts)
    lines.append(f"- **File totali**: {scan_result.total_files}")
    lines.append(f"- **Moduli rilevati**: {', '.join(scan_result.modules)}")
    lines.append(f"- **Linguaggi**: {lang_list}")
    if is_hybrid and module_plans:
        lines.append(f"- **Microservizi**: {len(module_plans)}")
    lines.append("")

    # Analisi statica (riusa il summary_text dell'analyzer)
    lines.append(analysis.summary_text())
    lines.append("")

    # File classificati per urgenza (P7)
    lines.append("## File classificati per urgenza\n")
    _append_urgency_file_list(lines, scan_result.files)

    # ── Istruzioni per l'agente ──────────────────────────────────────
    lines.append("---\n")
    lines.append("## Istruzioni per la generazione della documentazione\n")
    lines.append(
        "Sei un agente AI con accesso al filesystem del progetto. "
        "Hai a disposizione l'analisi strutturale sopra e puoi leggere qualsiasi file direttamente dalla workspace.\n\n"
        "**NON ti serve che il codice sia incollato nei prompt** — leggi i file dal filesystem quando necessario.\n"
    )

    if is_hybrid and module_plans:
        # Istruzioni multi-microservizio
        lines.append("### Piano di lavoro (progetto multi-microservizio)\n")
        lines.append("Devi generare i seguenti documenti Markdown:\n")

        for i, mod_name in enumerate(sorted(module_plans.keys()), 1):
            lines.append(f"**{i}. Microservizio `{mod_name}`**:")
            lines.append(f"   - `{mod_name}/specifica_funzionale.md`")
            lines.append(f"   - `{mod_name}/specifica_tecnica.md`")

        lines.append(f"\n**{len(module_plans) + 1}. Documenti d'insieme**:")
        lines.append(f"   - `architettura_sistema.md` — come i microservizi collaborano")
        lines.append(f"   - `specifica_funzionale_completa.md` — visione funzionale end-to-end")
        lines.append(f"   - `specifica_tecnica_completa.md` — visione tecnica end-to-end\n")

        lines.append("### Procedura:\n")
        lines.append("1. Per ogni microservizio, leggi i file 🔴 (obbligatori) e 🟡 (se necessario) dalla lista sopra")
        lines.append("2. Genera specifica funzionale e tecnica per quel microservizio")
        lines.append("3. Dopo aver completato tutti i microservizi, genera i documenti d'insieme")
        lines.append("4. Il documento di architettura si concentra sulle INTEGRAZIONI tra servizi\n")
    else:
        # Istruzioni progetto singolo
        lines.append("### Piano di lavoro\n")
        lines.append("Devi generare i seguenti documenti Markdown:\n")
        lines.append("1. `specifica_funzionale.md`")
        lines.append("2. `specifica_tecnica.md`\n")
        lines.append("### Procedura:\n")
        lines.append("1. Leggi i file 🔴 (obbligatori) e 🟡 (se necessario) dalla lista sopra")
        lines.append("2. Per i file business_critical, leggi SEMPRE il contenuto completo")
        lines.append("3. Genera i due documenti seguendo i template sotto\n")

    # Template documenti
    lines.append("---\n")
    lines.append("## Template: Specifica Funzionale\n")
    lines.append("Segui ESATTAMENTE questa struttura per il documento funzionale:\n")
    # Estraiamo solo la parte istruzioni dal template
    func_instructions = FUNCTIONAL_DOC.split("## Istruzioni")[1] if "## Istruzioni" in FUNCTIONAL_DOC else FUNCTIONAL_DOC
    lines.append(func_instructions.strip())
    lines.append("")

    lines.append("---\n")
    lines.append("## Template: Specifica Tecnica\n")
    lines.append("Segui ESATTAMENTE questa struttura per il documento tecnico:\n")
    tech_instructions = TECHNICAL_DOC.split("## Istruzioni")[1] if "## Istruzioni" in TECHNICAL_DOC else TECHNICAL_DOC
    lines.append(tech_instructions.strip())
    lines.append("")

    if is_hybrid and module_plans:
        lines.append("---\n")
        lines.append("## Template: Architettura di Sistema\n")
        lines.append("Segui ESATTAMENTE questa struttura per il documento di architettura:\n")
        arch_instructions = SYSTEM_ARCHITECTURE_DOC.split("## Istruzioni")[1] if "## Istruzioni" in SYSTEM_ARCHITECTURE_DOC else SYSTEM_ARCHITECTURE_DOC
        lines.append(arch_instructions.strip())
        lines.append("")

    # Output directory
    lines.append("---\n")
    lines.append(f"## Output\n")
    lines.append(f"Salva tutti i documenti generati in: `{config.output_dir}`\n")

    lines.append("---\n")
    lines.append("## Post-generazione: conversione DOCX e pulizia\n")
    lines.append(
        "Dopo aver generato TUTTI i documenti .md, esegui questi comandi nel terminale:\n\n"
        "### 1. Conversione in formato Word (.docx) con template aziendale\n\n"
        "```bash\n"
    )
    lines.append(f"python -m docgen --render {config.output_dir}/*.md"
                  f" --meta PROGETTO=\"{config.project_name}\"\n")
    lines.append(
        "```\n\n"
        "Puoi personalizzare i metadati della copertina aggiungendo parametri `--meta`:\n"
        "- `CLIENTE=\"Nome Cliente\"`\n"
        "- `PROGETTO=\"Nome Progetto\"`\n"
        "- `INTESTAZIONE_ENTE=\"Nome Ente\"`\n"
        "- `REDATTO_DA=\"Nome Autore\"`\n"
        "- `VERSIONE=\"1.0\"`\n\n"
        "### 2. Pulizia file temporanei\n\n"
        "```bash\n"
    )
    lines.append(f"python -m docgen --cleanup {config.output_dir}\n")
    lines.append(
        "```\n\n"
        "Questo rimuove i file di contesto (analisi_statica.md, docgen_context_*.md, "
        "docgen_files.json, docgen_index.md, docgen_instructions.md, struttura_progetto.txt) "
        "lasciando solo i documenti finali .md e .docx.\n"
    )

    return "\n".join(lines)


def _generate_files_json(
    scan_result: ScanResult,
    analysis: ProjectAnalysis,
    config: DocGenConfig,
    is_hybrid: bool,
) -> dict:
    """Genera il dizionario per docgen_files.json."""
    files_list = []
    for f in scan_result.files:
        entry: dict = {
            "path": f.path,
            "category": f.category,
            "module": f.module or "root",
            "priority": f.priority,
            "size_bytes": f.size_bytes,
        }
        if f.category == "business_critical":
            entry["detection_reason"] = _build_detection_reason(f)
        files_list.append(entry)

    endpoints_list = []
    for ep in analysis.endpoints:
        endpoints_list.append({
            "method": ep.method,
            "path": ep.path,
            "handler": ep.handler,
            "file": ep.file,
        })

    entities_list = []
    for ent in analysis.entities:
        entities_list.append({
            "name": ent.name,
            "table": ent.table,
            "fields": ent.fields,
            "file": ent.file,
        })

    routes_list = []
    for r in analysis.routes:
        routes_list.append({
            "path": r.path,
            "component": r.component,
            "lazy": r.lazy,
            "file": r.file,
        })

    deps: dict = {}
    if analysis.maven_deps:
        deps["maven"] = [{"name": d.name, "version": d.version} for d in analysis.maven_deps]
    if analysis.npm_deps:
        deps["npm"] = [{"name": d.name, "version": d.version} for d in analysis.npm_deps]
    if analysis.nuget_deps:
        deps["nuget"] = [{"name": d.name, "version": d.version} for d in analysis.nuget_deps]
    if analysis.generic_deps:
        for d in analysis.generic_deps:
            scope = d.scope or "other"
            deps.setdefault(scope, []).append({"name": d.name, "version": d.version})

    db_config: dict = {}
    if analysis.db_info.url:
        db_config["url"] = analysis.db_info.url
        if analysis.db_info.driver:
            db_config["driver"] = analysis.db_info.driver
        if analysis.db_info.ddl_auto:
            db_config["ddl_auto"] = analysis.db_info.ddl_auto
        if analysis.db_info.port:
            db_config["port"] = analysis.db_info.port

    return {
        "project_name": config.project_name,
        "project_path": config.project_path,
        "generated_at": datetime.now().isoformat(),
        "modules": scan_result.modules,
        "is_multi_microservice": is_hybrid,
        "statistics": {
            "total_files": scan_result.total_files,
            "total_chars": scan_result.total_chars,
            "skipped_files": scan_result.skipped_count,
            "languages": dict(scan_result.top_extensions(20)),
        },
        "files": files_list,
        "endpoints": endpoints_list,
        "entities": entities_list,
        "routes": routes_list,
        "dependencies": deps,
        "config": db_config,
    }


def _agent_export(
    scan_result: ScanResult,
    analysis: ProjectAnalysis,
    config: DocGenConfig,
    is_hybrid: bool,
    module_plans: dict[str, ChunkPlan] | None,
    mode: str = _modes.DOCS,
    test_analysis: 'TestStaticAnalysis | None' = None,
) -> None:
    """Esegue l'export per modalità agent-ready.

    Per progetti multi-microservizio (P6): genera file separati per modulo.
    Per progetti singoli: genera docgen_context.md monolitico.
    Il parametro `mode` determina il contenuto delle istruzioni e dei contesti.
    """
    from .analyzer import TestStaticAnalysis
    out_path = Path(config.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if is_hybrid and module_plans:
        # ── P6: export per-microservizio ─────────────────────────────
        sorted_modules = sorted(module_plans.keys())
        by_module = scan_result.files_by_module()

        # 1. docgen_instructions.md — istruzioni + template (contenuto dipende da mode)
        if mode == _modes.TESTS:
            instr_md = _generate_instructions_md_tests(config, sorted_modules, test_analysis)
        else:
            instr_md = _generate_instructions_md_docs(config, sorted_modules)
        instr_path = out_path / "docgen_instructions.md"
        instr_path.write_text(instr_md, encoding="utf-8")
        console.print(f"  [green]✓[/green] {instr_path.name} ({len(instr_md):,} caratteri)")

        # 2. docgen_context_{module}.md — uno per microservizio (contenuto dipende da mode)
        for mod_name in sorted_modules:
            mod_files = by_module.get(mod_name, [])
            if mode == _modes.TESTS:
                mod_md = _generate_module_context_md_tests(
                    mod_name, mod_files, analysis, test_analysis, config
                )
            else:
                mod_md = _generate_module_context_md(mod_name, mod_files, analysis, config)
            mod_path = out_path / f"docgen_context_{mod_name}.md"
            mod_path.write_text(mod_md, encoding="utf-8")
            console.print(f"  [green]✓[/green] {mod_path.name} ({len(mod_md):,} caratteri, {len(mod_files)} file)")

        # 3. docgen_index.md — indice file generati
        index_md = _generate_index_md(config, sorted_modules, is_hybrid=True)
        index_path = out_path / "docgen_index.md"
        index_path.write_text(index_md, encoding="utf-8")
        console.print(f"  [green]✓[/green] {index_path.name}")

        # 4. docgen_files.json — dati machine-readable (come prima)
        files_data = _generate_files_json(scan_result, analysis, config, is_hybrid)
        json_path = out_path / "docgen_files.json"
        json_path.write_text(
            json.dumps(files_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(f"  [green]✓[/green] {json_path.name} ({len(files_data['files'])} file)")

        mode_label = "analisi test" if mode == _modes.TESTS else "documentazione"
        if mode == _modes.TESTS:
            n_docs = f"{len(module_plans)} analisi test (una per microservizio) + 1 documento sistema"
        else:
            n_docs = f"{len(module_plans) * 2 + 3} documenti ({len(module_plans)} microservizi × 2 + 3 d'insieme)"
        n_files = 3 + len(sorted_modules)  # instructions + N contexts + index + json
        console.print(Panel(
            f"[bold green]Agent export completato![/bold green]\n\n"
            f"Modalità: [bold]{mode}[/bold] ({mode_label})\n"
            f"File generati: {n_files + 1}\n"
            f"  • [bold]docgen_instructions.md[/bold] — istruzioni + template\n"
            + "".join(f"  • [bold]docgen_context_{m}.md[/bold] — contesto {m}\n" for m in sorted_modules)
            + f"  • [bold]docgen_index.md[/bold] — indice\n"
            f"  • [bold]docgen_files.json[/bold] — dati machine-readable\n\n"
            f"Documenti da generare: {n_docs}\n"
            f"Output in: {config.output_dir}\n\n"
            f"[bold]Come usare:[/bold]\n"
            f"Passa `docgen_instructions.md` come prompt iniziale all'agente.\n"
            f"L'agente leggerà i file `docgen_context_*.md` per ogni microservizio.",
            border_style="green",
        ))
    else:
        # ── Export progetto singolo ───────────────────────────────────
        # 1. docgen_context.md (contenuto dipende da mode)
        if mode == _modes.TESTS:
            context_md = _generate_context_md_tests(
                scan_result, analysis, test_analysis, config, is_hybrid, module_plans
            )
        else:
            context_md = _generate_context_md(scan_result, analysis, config, is_hybrid, module_plans)
        context_path = out_path / "docgen_context.md"
        context_path.write_text(context_md, encoding="utf-8")
        console.print(f"  [green]✓[/green] {context_path.name} ({len(context_md):,} caratteri)")

        # 2. docgen_files.json
        files_data = _generate_files_json(scan_result, analysis, config, is_hybrid)
        json_path = out_path / "docgen_files.json"
        json_path.write_text(
            json.dumps(files_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(f"  [green]✓[/green] {json_path.name} ({len(files_data['files'])} file)")

        # 3. docgen_index.md
        index_md = _generate_index_md(config, [], is_hybrid=False)
        index_path = out_path / "docgen_index.md"
        index_path.write_text(index_md, encoding="utf-8")
        console.print(f"  [green]✓[/green] {index_path.name}")

        mode_label = "analisi test" if mode == _modes.TESTS else "documentazione"
        if mode == _modes.TESTS:
            docs_note = "1 documento (`analisi_test.md`)"
        else:
            docs_note = "2 documenti (`specifica_funzionale.md` + `specifica_tecnica.md`)"
        console.print(Panel(
            f"[bold green]Agent export completato![/bold green]\n\n"
            f"Modalità: [bold]{mode}[/bold] ({mode_label})\n"
            f"File generati:\n"
            f"  • [bold]{context_path.name}[/bold] — contesto strutturato + istruzioni + template\n"
            f"  • [bold]{json_path.name}[/bold] — dati machine-readable\n"
            f"  • [bold]{index_path.name}[/bold] — indice\n\n"
            f"Documenti da generare: {docs_note}\n"
            f"Output in: {config.output_dir}\n\n"
            f"[bold]Come usare:[/bold]\n"
            f"Passa `docgen_context.md` come prompt all'agente (Copilot, Kilo Code, Claude Code).\n"
            f"L'agente leggerà i file dal workspace e genererà la documentazione.",
            border_style="green",
        ))


def _parse_meta_args(meta_args: list[str] | None) -> dict[str, str]:
    """Parsa gli argomenti --meta KEY=VALUE in un dizionario."""
    if not meta_args:
        return {}
    result: dict[str, str] = {}
    for item in meta_args:
        if "=" in item:
            key, value = item.split("=", 1)
            result[key.strip()] = value.strip()
    return result


def _handle_render(args: argparse.Namespace) -> None:
    """Gestisce la modalità --render: converte .md → .docx con template aziendale."""
    from .template_renderer import render_md_to_docx

    _print_banner()
    console.print("\n[bold yellow]Rendering .md → .docx con template aziendale[/bold yellow]\n")

    metadata = _parse_meta_args(args.meta)
    # Se è specificato --name, usalo come PROGETTO
    if hasattr(args, "name") and args.name:
        metadata.setdefault("PROGETTO", args.name)

    template_path = args.template
    generated: list[str] = []

    for md_file in args.render:
        md_path = Path(md_file)

        # Supporta glob pattern
        if "*" in str(md_path):
            parent = md_path.parent if md_path.parent != md_path else Path(".")
            matches = list(parent.glob(md_path.name))
            if not matches:
                console.print(f"  [yellow]⚠[/yellow] Nessun match per: {md_file}")
            for m in matches:
                if m.suffix == ".md":
                    out_path = m.with_suffix(".docx")
                    try:
                        result = render_md_to_docx(str(m), str(out_path), template_path, metadata)
                        generated.append(result)
                        console.print(f"  [green]✓[/green] {out_path.name}")
                    except Exception as e:
                        console.print(f"  [red]✗[/red] {m.name}: {e}")
        else:
            if not md_path.exists():
                console.print(f"  [red]✗[/red] File non trovato: {md_file}")
                continue
            out_path = md_path.with_suffix(".docx")
            try:
                result = render_md_to_docx(str(md_path), str(out_path), template_path, metadata)
                generated.append(result)
                console.print(f"  [green]✓[/green] {out_path.name}")
            except Exception as e:
                console.print(f"  [red]✗[/red] {md_path.name}: {e}")

    if generated:
        console.print(Panel(
            f"[bold green]Rendering completato![/bold green]\n"
            f"File .docx generati: {len(generated)}",
            border_style="green",
        ))
    else:
        console.print("[red]Nessun file convertito.[/red]")


def _handle_cleanup(args: argparse.Namespace) -> None:
    """Gestisce la modalità --cleanup: rimuove i file temporanei dell'agent-export."""
    import glob as glob_module

    _print_banner()

    # Determina la directory
    if args.cleanup == "AUTO":
        # Usa output_dir dal project_path se disponibile
        if hasattr(args, "project_path") and args.project_path:
            cleanup_dir = Path(os.path.abspath(args.project_path)) / "DocGen"
        else:
            console.print("[red]Errore: specifica la directory di output per --cleanup[/red]")
            sys.exit(1)
    else:
        cleanup_dir = Path(os.path.abspath(args.cleanup))

    if not cleanup_dir.exists():
        console.print(f"[red]Directory non trovata: {cleanup_dir}[/red]")
        sys.exit(1)

    console.print(f"\n[bold yellow]Pulizia file temporanei[/bold yellow] in: {cleanup_dir}\n")

    removed: list[str] = []

    # File con nome esatto
    for fname in AGENT_EXPORT_TEMP_FILES:
        fpath = cleanup_dir / fname
        if fpath.exists():
            fpath.unlink()
            removed.append(fname)
            console.print(f"  [red]✗[/red] {fname}")

    # Pattern glob
    for pattern in AGENT_EXPORT_TEMP_PATTERNS:
        for match in cleanup_dir.glob(pattern):
            match.unlink()
            removed.append(match.name)
            console.print(f"  [red]✗[/red] {match.name}")

    if removed:
        console.print(Panel(
            f"[bold green]Pulizia completata![/bold green]\n"
            f"File rimossi: {len(removed)}",
            border_style="green",
        ))
    else:
        console.print("[yellow]Nessun file temporaneo trovato.[/yellow]")


def build_config(args: argparse.Namespace) -> DocGenConfig:
    """Costruisce la configurazione dal namespace argparse."""
    if not args.project_path:
        console.print("[red]Errore: specifica il path del progetto da analizzare[/red]")
        sys.exit(1)

    project_path = os.path.abspath(args.project_path)

    if not os.path.isdir(project_path):
        console.print(f"[red]Errore: '{project_path}' non è una directory valida[/red]")
        sys.exit(1)

    project_name = args.name or os.path.basename(project_path)

    # Default: crea la cartella DocGen nella root del progetto analizzato
    if args.output is None:
        output_dir = os.path.join(project_path, "DocGen")
    else:
        output_dir = os.path.abspath(args.output)

    return DocGenConfig(
        project_path=project_path,
        project_name=project_name,
        output_dir=output_dir,
        output_format=args.format,
        model=args.model,
        dry_run=args.dry_run,
        max_tokens=args.max_tokens,
        chunk_budget=args.chunk_budget,
        export_prompts=False,
        llm_bridge=False,
        agent_export=args.agent_export,
        mode=getattr(args, "mode", _modes.DOCS) or _modes.DOCS,
    )


def _select_mode_interactive() -> str:
    """Chiede interattivamente all'utente quale modalità utilizzare."""
    console.print(Panel(
        "[bold yellow]Seleziona la modalità operativa[/bold yellow]\n\n"
        + "\n".join(
            f"  [bold cyan][{i}][/bold cyan]  [bold]{k}[/bold] — {v}"
            for i, (k, v) in enumerate(_modes.AVAILABLE_MODES.items(), 1)
        ),
        border_style="yellow",
    ))

    mode_keys = list(_modes.AVAILABLE_MODES.keys())
    while True:
        choice = console.input(
            f"[bold]Modalità (1–{len(mode_keys)}): [/bold]"
        ).strip()
        if choice.isdigit() and 1 <= int(choice) <= len(mode_keys):
            selected = mode_keys[int(choice) - 1]
            console.print(f"\n  Modalità selezionata: [bold green]{selected}[/bold green]\n")
            return selected
        # Accetta anche il nome diretto
        if choice in mode_keys:
            return choice
        console.print(f"[red]Scelta non valida. Inserisci un numero da 1 a {len(mode_keys)}.[/red]")


def _print_test_analysis(test_analysis: 'TestStaticAnalysis') -> None:
    """Stampa un riepilogo dell'analisi estesa per la modalità tests."""
    from rich.table import Table as _Table
    console.print(f"\n[bold]🧪 Analisi estesa per test[/bold]")
    table = _Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="cyan")
    table.add_column()
    table.add_row("Firme di metodi", str(len(test_analysis.method_signatures)))
    table.add_row("Regole di validazione", str(len(test_analysis.validation_rules)))
    table.add_row("Regole di sicurezza", str(len(test_analysis.security_rules)))
    table.add_row("Enumerazioni", str(len(test_analysis.enums)))
    table.add_row("Chiamate esterne", str(len(test_analysis.external_calls)))
    table.add_row("Eccezioni (lanciate)", str(sum(1 for e in test_analysis.exceptions if e.is_thrown)))
    table.add_row("Eccezioni (gestite)", str(sum(1 for e in test_analysis.exceptions if not e.is_thrown)))
    console.print(table)


def main() -> None:
    """Entry point CLI."""
    parser = argparse.ArgumentParser(
        prog="docgen",
        description="DocGen — Genera documentazione professionale da codebase",
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=None,
        help="Path al progetto da analizzare",
    )
    parser.add_argument(
        "-n", "--name",
        help="Nome del progetto (default: nome directory)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Directory output (default: <progetto>/DocGen)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["all", "md", "docx"],
        default="all",
        help="Formato output (default: all)",
    )
    parser.add_argument(
        "-m", "--model",
        default="claude-sonnet-4-20250514",
        help="Modello Claude da usare",
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Solo analisi, nessuna chiamata API",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=200_000,
        help="Max token contesto modello (default: 200000)",
    )
    parser.add_argument(
        "--chunk-budget",
        type=int,
        default=80_000,
        help="Budget token per chunk (default: 80000)",
    )
    parser.add_argument(
        "--mode",
        choices=list(_modes.AVAILABLE_MODES.keys()),
        default=None,
        help=(
            "Modalità operativa: "
            + " | ".join(f"{k} ({v})" for k, v in _modes.AVAILABLE_MODES.items())
            + ". Se omesso, viene chiesto interattivamente."
        ),
    )
    parser.add_argument(
        "--agent-export",
        action="store_true",
        help="Esporta contesto strutturato per agenti AI (Copilot, Kilo Code, Claude Code) — nessuna chiamata API",
    )
    parser.add_argument(
        "--render",
        nargs="+",
        metavar="MD_FILE",
        help="Converte uno o più file .md in .docx usando il template aziendale",
    )
    parser.add_argument(
        "--template",
        default=None,
        help="Path al template .docx aziendale (default: templates/template_aziendale.docx)",
    )
    parser.add_argument(
        "--cleanup",
        metavar="OUTPUT_DIR",
        nargs="?",
        const="AUTO",
        help="Rimuove i file temporanei dell'agent-export dalla directory di output",
    )
    parser.add_argument(
        "--meta",
        nargs="*",
        metavar="KEY=VALUE",
        help="Metadati per i placeholder del template (es. --meta CLIENTE=Acme PROGETTO='Mio Progetto')",
    )

    args = parser.parse_args()

    # ── Modalità --render: converte .md → .docx e esce ───────────────
    if args.render:
        _handle_render(args)
        return

    # ── Modalità --cleanup: rimuove file temporanei e esce ───────────
    if args.cleanup:
        _handle_cleanup(args)
        return

    # ── Selezione modalità (interattiva se non fornita) ───────────────
    if not args.mode:
        if sys.stdin.isatty():
            args.mode = _select_mode_interactive()
        else:
            # Contesto non interattivo (script/skill): default a docs
            args.mode = _modes.DOCS

    config = build_config(args)

    _print_banner()

    # ── Step 1: Scansione ────────────────────────────────────────────────
    console.print(f"\n[bold yellow]Step 1/4[/bold yellow] — Scansione progetto: {config.project_path}\n")
    scan_result = scan_project(config)

    if scan_result.total_files == 0:
        console.print("[red]Nessun file sorgente trovato nel progetto.[/red]")
        sys.exit(1)

    _print_scan_stats(scan_result, config)
    _print_category_table(scan_result)

    # ── Step 2: Analisi statica ──────────────────────────────────────────
    console.print(f"\n[bold yellow]Step 2/4[/bold yellow] — Analisi statica\n")
    analysis = analyze_project(scan_result)
    _print_analysis(analysis)

    # ── Step 2b: Analisi estesa per modalità tests ────────────────────────
    test_analysis = None
    if config.mode == _modes.TESTS:
        from .analyzer import analyze_project_for_tests
        console.print(f"\n[bold yellow]Step 2b[/bold yellow] — Analisi estesa per test\n")
        test_analysis = analyze_project_for_tests(scan_result)
        _print_test_analysis(test_analysis)

    # ── Step 3: Pianificazione chunk ─────────────────────────────────────
    console.print(f"\n[bold yellow]Step 3/4[/bold yellow] — Pianificazione chunk\n")
    chunk_plan = create_chunks(scan_result, config)

    # Calcola token dell'analisi statica (inviata come contesto in ogni chiamata API)
    analysis_tokens = config.chars_to_tokens(len(analysis.summary_text()))

    _print_chunk_plan(chunk_plan, analysis_tokens)

    # Salva output statici
    console.print(f"\n[bold]💾 Salvataggio file statici[/bold]")
    _save_static_outputs(scan_result, analysis, config.output_dir)

    # ── Rilevamento progetto multi-microservizio ───────────────────────
    is_hybrid_candidate = _is_large_project(scan_result, chunk_plan)
    module_plans: dict[str, ChunkPlan] | None = None

    if is_hybrid_candidate:
        module_plans = _create_module_chunk_plans(scan_result, config)
        _print_hybrid_plan(module_plans, analysis_tokens)

    # ── Dry run: fine qui ────────────────────────────────────────────────
    if config.dry_run:
        mode_label = f"  Modalità: [bold]{config.mode}[/bold]\n"
        hybrid_note = ""
        if is_hybrid_candidate:
            hybrid_note = "\n[yellow]Modalità ibrida disponibile: per-microservizio + architettura di sistema[/yellow]"
        console.print(Panel(
            "[bold green]Dry run completato![/bold green]\n"
            f"{mode_label}"
            "Nessuna chiamata API effettuata.\n"
            f"Output in: {config.output_dir}"
            + hybrid_note,
            border_style="green",
        ))
        return

    # ── Agent export: genera context + json e stop ───────────────────────
    if config.agent_export:
        console.print(
            f"\n[bold yellow]Step 4/4[/bold yellow] — Agent export "
            f"[dim](modalità: {config.mode})[/dim]\n"
        )
        _agent_export(
            scan_result, analysis, config,
            is_hybrid=is_hybrid_candidate,
            module_plans=module_plans,
            mode=config.mode,
            test_analysis=test_analysis,
        )
        return

    # ── Step 4: Generazione documenti ────────────────────────────────────
    call_fn = None  # Default: usa Claude API direttamente

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print(
            "[red]Errore: ANTHROPIC_API_KEY non configurata.[/red]\n"
            "Imposta la variabile d'ambiente: export ANTHROPIC_API_KEY=sk-..."
        )
        sys.exit(1)

    # Scelta modalità per progetti grandi
    generation_mode = "unified"
    if is_hybrid_candidate and module_plans:
        generation_mode = _ask_generation_mode(scan_result, chunk_plan, module_plans, analysis_tokens)
        if generation_mode == "cancel":
            console.print("[yellow]Generazione annullata.[/yellow]")
            return

    console.print(f"\n[bold yellow]Step 4/4[/bold yellow] — Generazione documenti con Claude\n")

    from .generator import generate_documents, generate_documents_hybrid
    from .renderer import render_documents, render_documents_hybrid

    if generation_mode == "hybrid" and module_plans:
        # ── Modalità ibrida ──────────────────────────────────────────
        results = generate_documents_hybrid(module_plans, analysis, config, call_fn=call_fn)

        console.print(f"\n[bold]📄 Rendering documenti[/bold]")
        generated = render_documents_hybrid(
            results,
            config.output_dir,
            config.project_name,
            config.output_format,
        )

        console.print(Panel(
            f"[bold green]Generazione ibrida completata![/bold green]\n"
            f"Microservizi documentati: {len(module_plans)}\n"
            f"File generati: {len(generated)}\n"
            f"Output in: {config.output_dir}",
            border_style="green",
        ))
    else:
        # ── Modalità classica (unificata) ────────────────────────────
        functional_md, technical_md = generate_documents(chunk_plan, analysis, config, call_fn=call_fn)

        console.print(f"\n[bold]📄 Rendering documenti[/bold]")
        generated = render_documents(
            functional_md,
            technical_md,
            config.output_dir,
            config.project_name,
            config.output_format,
        )

        console.print(Panel(
            f"[bold green]Generazione completata![/bold green]\n"
            f"File generati: {len(generated)}\n"
            f"Output in: {config.output_dir}",
            border_style="green",
        ))


if __name__ == "__main__":
    main()
