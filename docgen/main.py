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
)
from .generator import smart_truncate

console = Console()


def _print_banner() -> None:
    console.print(Panel.fit(
        "[bold blue]DocGen[/bold blue] — Generatore Automatico di Documentazione\n"
        "[dim]Analizza codebase e genera documentazione professionale per la PA[/dim]",
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
    """Rileva se il progetto è grande abbastanza per suggerire la modalità ibrida."""
    n_modules = len(scan_result.modules)
    n_chunks = chunk_plan.total_chunks
    return (
        n_modules >= LARGE_PROJECT_MIN_MODULES
        and n_chunks >= LARGE_PROJECT_MIN_CHUNKS
    )


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
        phase23_output = 16000  # 8K per doc

        # Fase summary — input = analisi troncate + prompt (no static)
        summary_input = min(phase1_output, 100_000) + 3000 + call_overhead
        summary_output = 2000  # max_output_tokens=2048

        total_input += phase1_input + (synthesis_input_per_doc * 2) + summary_input
        total_output += phase1_output + phase23_output + summary_output

    # Doc architettura sistema — riceve tutti i summary + static + prompt
    arch_input = len(module_plans) * 1500 + static_tokens + 3000 + call_overhead
    total_input += arch_input
    total_output += 8000

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

    # File classificati per categoria, raggruppati per priorità
    lines.append("## File classificati per categoria\n")
    by_cat = scan_result.files_by_category()

    # Ordina: business_critical prima, poi per priorità
    priority_order = {"alta": 0, "media": 1, "bassa": 2}
    sorted_cats = sorted(
        by_cat.keys(),
        key=lambda c: (0 if c == "business_critical" else 1, priority_order.get(
            by_cat[c][0].priority if by_cat[c] else "bassa", 2
        ), c),
    )

    for cat in sorted_cats:
        files = by_cat[cat]
        if not files:
            continue
        prio = files[0].priority
        label = "ALTA — leggere OBBLIGATORIAMENTE" if prio == "alta" else (
            "MEDIA" if prio == "media" else "BASSA — leggere solo se necessario"
        )
        lines.append(f"### {cat} (priorità {label})\n")
        for f in sorted(files, key=lambda x: x.path):
            extra = ""
            if cat == "business_critical":
                reason = _build_detection_reason(f)
                extra = f" → {reason}" if reason else ""
            lines.append(f"- `{f.path}`{extra}")
        lines.append("")

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
        lines.append("1. Per ogni microservizio, leggi i file con priorità ALTA e MEDIA dalla lista sopra")
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
        lines.append("1. Leggi i file con priorità ALTA e MEDIA dalla lista sopra")
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
) -> None:
    """Esegue l'export per modalità agent-ready."""
    out_path = Path(config.output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. docgen_context.md
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

    # Riepilogo
    n_docs = "5 documenti" if is_hybrid and module_plans else "2 documenti"
    if is_hybrid and module_plans:
        n_docs = f"{len(module_plans) * 2 + 3} documenti ({len(module_plans)} microservizi × 2 + 3 d'insieme)"

    console.print(Panel(
        f"[bold green]Agent export completato![/bold green]\n\n"
        f"File generati:\n"
        f"  • [bold]{context_path.name}[/bold] — contesto strutturato + istruzioni + template\n"
        f"  • [bold]{json_path.name}[/bold] — dati machine-readable\n\n"
        f"Documenti da generare: {n_docs}\n"
        f"Output in: {config.output_dir}\n\n"
        f"[bold]Come usare:[/bold]\n"
        f"Passa `docgen_context.md` come prompt all'agente (Copilot, Kilo Code, Claude Code).\n"
        f"L'agente leggerà i file dal workspace e genererà la documentazione.",
        border_style="green",
    ))


def build_config(args: argparse.Namespace) -> DocGenConfig:
    """Costruisce la configurazione dal namespace argparse."""
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
        export_prompts=args.export_prompts,
        llm_bridge=args.llm_bridge,
        agent_export=args.agent_export,
    )


def main() -> None:
    """Entry point CLI."""
    parser = argparse.ArgumentParser(
        prog="docgen",
        description="DocGen — Genera documentazione professionale da codebase",
    )
    parser.add_argument(
        "project_path",
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
        "--export-prompts",
        action="store_true",
        help="Esporta i prompt pronti da usare con altri LLM (Kilo Code, ChatGPT, ecc.)",
    )
    parser.add_argument(
        "--llm-bridge",
        action="store_true",
        help="Modalità bridge: scambia prompt/risposta via file per integrazione con Kilo Code o altri agenti",
    )
    parser.add_argument(
        "--agent-export",
        action="store_true",
        help="Esporta contesto strutturato per agenti AI (Copilot, Kilo Code, Claude Code) — nessuna chiamata API",
    )

    args = parser.parse_args()
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
        mode_label = ""
        if is_hybrid_candidate:
            mode_label = (
                "\n[yellow]Modalità ibrida disponibile: per-microservizio + architettura di sistema[/yellow]"
            )
        console.print(Panel(
            "[bold green]Dry run completato![/bold green]\n"
            "Nessuna chiamata API effettuata.\n"
            f"Output in: {config.output_dir}"
            + mode_label,
            border_style="green",
        ))
        return

    # ── Agent export: genera context + json e stop ───────────────────────
    if config.agent_export:
        console.print(
            f"\n[bold yellow]Step 4/4[/bold yellow] — Agent export\n"
        )
        _agent_export(
            scan_result, analysis, config,
            is_hybrid=is_hybrid_candidate,
            module_plans=module_plans,
        )
        return

    # ── Export prompts: genera i file prompt e stop ──────────────────────
    if config.export_prompts:
        console.print(
            f"\n[bold yellow]Step 4/4[/bold yellow] — Esportazione prompt\n"
        )

        if is_hybrid_candidate and module_plans:
            exported = _export_prompts_hybrid(module_plans, analysis, config)
        else:
            exported = _export_prompts_unified(chunk_plan, analysis, config)

        prompts_dir = Path(config.output_dir) / "prompts"
        console.print(Panel(
            f"[bold green]Prompt esportati![/bold green]\n"
            f"File generati: {len(exported)}\n"
            f"Directory: {prompts_dir}\n\n"
            "[bold]Come usare i prompt:[/bold]\n"
            "1. Apri 00_SYSTEM_PROMPT.md e incollalo come system prompt\n"
            "2. Invia i prompt 01_ANALISI_CHUNK_*.md uno alla volta\n"
            "3. Raccogli le risposte e incollale nei prompt 02/03\n"
            "4. Per l'architettura: genera prima i riepiloghi (04_*)",
            border_style="green",
        ))
        return

    # ── Step 4: Generazione documenti ────────────────────────────────────
    call_fn = None  # Default: usa Claude API direttamente

    if config.llm_bridge:
        # Modalità bridge: niente API key necessaria
        from .generator import _call_bridge
        call_fn = _call_bridge

        bridge_dir = Path(config.output_dir) / ".bridge"
        console.print(Panel(
            "[bold cyan]Modalità LLM Bridge attiva[/bold cyan]\n\n"
            f"Directory bridge: {bridge_dir}\n\n"
            "Lo script scriverà i prompt in file numerati e attenderà le risposte.\n"
            "Un agente esterno (Kilo Code, ecc.) deve:\n"
            "1. Leggere il file system_prompt.md come contesto di sistema\n"
            "2. Quando compare READY, leggere prompt_NNN.md\n"
            "3. Processare il prompt col proprio LLM\n"
            "4. Salvare la risposta in response_NNN.md",
            border_style="cyan",
        ))
    else:
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

    label = "con LLM Bridge" if config.llm_bridge else "con Claude"
    console.print(f"\n[bold yellow]Step 4/4[/bold yellow] — Generazione documenti {label}\n")

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
