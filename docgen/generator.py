"""Generator — chiamate Claude API con retry, logging e progress bar."""

from __future__ import annotations

import os
import time
import logging
from pathlib import Path
from typing import Callable

from anthropic import Anthropic, APIError, RateLimitError, APIConnectionError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from .config import DocGenConfig, CHARS_PER_TOKEN, COST_INPUT_PER_M, COST_OUTPUT_PER_M
from .chunker import ChunkPlan, Chunk
from .analyzer import ProjectAnalysis
from .prompts import (
    SYSTEM_PROMPT, ANALYZE_CHUNK, FUNCTIONAL_DOC, TECHNICAL_DOC,
    SYSTEM_ARCHITECTURE_DOC, SERVICE_SUMMARY,
)

console = Console()
logger = logging.getLogger("docgen.generator")

# Retry config
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # secondi

# Tipo per la funzione di chiamata LLM
LlmCallFn = Callable[[object, DocGenConfig, str, int], tuple[str, int, int]]


def smart_truncate(text: str, max_chars: int) -> str:
    """Tronca testo mantenendo inizio e fine di ogni sezione."""
    if len(text) <= max_chars:
        return text

    # Dividi per sezioni (### header)
    sections = text.split("\n### ")
    if len(sections) <= 1:
        keep = max_chars // 2
        return text[:keep] + "\n\n[... TRONCATO ...]\n\n" + text[-keep:]

    # Budget per sezione
    budget_per_section = max_chars // len(sections)
    truncated_sections: list[str] = []

    for i, section in enumerate(sections):
        prefix = "### " if i > 0 else ""
        if len(section) <= budget_per_section:
            truncated_sections.append(prefix + section)
        else:
            keep = budget_per_section // 2
            truncated_sections.append(
                prefix + section[:keep] + "\n[... troncato ...]\n" + section[-keep:]
            )

    return "\n".join(truncated_sections)


def _call_claude(
    client: Anthropic,
    config: DocGenConfig,
    user_prompt: str,
    max_output_tokens: int = 8192,
) -> tuple[str, int, int]:
    """Chiama Claude API con retry esponenziale.
    
    Ritorna (response_text, input_tokens, output_tokens).
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=max_output_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            text = response.content[0].text
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens

            cost = config.estimate_cost(input_tokens, output_tokens)
            logger.info(
                f"API call: {input_tokens:,} in / {output_tokens:,} out — ${cost:.4f}"
            )

            return text, input_tokens, output_tokens

        except RateLimitError:
            wait = INITIAL_BACKOFF * (2 ** (attempt - 1))
            console.print(
                f"  [yellow]Rate limit raggiunto, attendo {wait}s "
                f"(tentativo {attempt}/{MAX_RETRIES})[/yellow]"
            )
            time.sleep(wait)

        except APIConnectionError:
            wait = INITIAL_BACKOFF * (2 ** (attempt - 1))
            console.print(
                f"  [yellow]Errore connessione, riprovo tra {wait}s "
                f"(tentativo {attempt}/{MAX_RETRIES})[/yellow]"
            )
            time.sleep(wait)

        except APIError as e:
            console.print(f"  [red]Errore API: {e}[/red]")
            if attempt == MAX_RETRIES:
                raise
            wait = INITIAL_BACKOFF * (2 ** (attempt - 1))
            time.sleep(wait)

    raise RuntimeError(f"Chiamata API fallita dopo {MAX_RETRIES} tentativi")


# ═══════════════════════════════════════════════════════════════════════════════
# Bridge caller — scambia prompt/risposta via file system
# ═══════════════════════════════════════════════════════════════════════════════

_bridge_call_counter = 0


def _call_bridge(
    _client: object,
    config: DocGenConfig,
    user_prompt: str,
    max_output_tokens: int = 8192,
) -> tuple[str, int, int]:
    """Scrive il prompt su file e attende la risposta da un agente esterno.

    Protocollo:
    1. Scrive system_prompt.md (una volta sola) + prompt_NNN.md
    2. Crea il file segnale READY
    3. Attende che compaia response_NNN.md
    4. Legge la risposta, cancella i segnali, prosegue

    Ritorna (response_text, estimated_input_tokens, estimated_output_tokens).
    """
    global _bridge_call_counter
    _bridge_call_counter += 1
    call_id = _bridge_call_counter

    bridge_dir = Path(config.output_dir) / ".bridge"
    bridge_dir.mkdir(parents=True, exist_ok=True)

    # Scrivi system prompt (solo alla prima chiamata)
    sys_path = bridge_dir / "system_prompt.md"
    if not sys_path.exists():
        sys_path.write_text(SYSTEM_PROMPT, encoding="utf-8")

    # Scrivi il prompt
    prompt_path = bridge_dir / f"prompt_{call_id:03d}.md"
    prompt_path.write_text(user_prompt, encoding="utf-8")

    # Scrivi il file segnale READY
    ready_path = bridge_dir / "READY"
    ready_path.write_text(
        f"{call_id}\n{prompt_path.name}\n",
        encoding="utf-8",
    )

    response_path = bridge_dir / f"response_{call_id:03d}.md"

    console.print(
        f"  [bold cyan]⏳ Bridge #{call_id}[/bold cyan] — "
        f"Prompt scritto in: {prompt_path.name}"
    )
    console.print(
        f"  [yellow]In attesa della risposta in: {response_path.name}[/yellow]"
    )

    # Poll per la risposta
    poll_interval = 2  # secondi
    waited = 0
    while not response_path.exists():
        time.sleep(poll_interval)
        waited += poll_interval
        if waited % 30 == 0:
            console.print(
                f"  [dim]... ancora in attesa ({waited}s). "
                f"Scrivi la risposta in {response_path.name}[/dim]"
            )

    # Leggi la risposta
    response_text = response_path.read_text(encoding="utf-8").strip()

    # Cleanup segnale READY
    if ready_path.exists():
        ready_path.unlink()

    # Stima token (approssimativa, non abbiamo i conteggi reali)
    est_input = int(len(user_prompt) / CHARS_PER_TOKEN)
    est_output = int(len(response_text) / CHARS_PER_TOKEN)

    console.print(
        f"  [green]✓ Bridge #{call_id}[/green] — "
        f"Risposta ricevuta ({len(response_text):,} caratteri)"
    )

    return response_text, est_input, est_output


def generate_documents(
    chunk_plan: ChunkPlan,
    analysis: ProjectAnalysis,
    config: DocGenConfig,
    call_fn: LlmCallFn | None = None,
) -> tuple[str, str]:
    """Genera i documenti funzionale e tecnico.
    
    Fase 1: Analizza ogni chunk
    Fase 2: Genera documento funzionale
    Fase 3: Genera documento tecnico
    
    Ritorna (functional_doc_md, technical_doc_md).
    """
    if call_fn is None:
        client = Anthropic()  # Usa ANTHROPIC_API_KEY da env
        call_fn = _call_claude
    else:
        client = None  # Bridge non usa il client
    static_analysis_text = analysis.summary_text()

    total_input_tokens = 0
    total_output_tokens = 0
    chunk_analyses: list[str] = []

    # ── Fase 1: Analisi per chunk ────────────────────────────────────────
    console.print("\n[bold cyan]Fase 1/3[/bold cyan] — Analisi moduli per chunk\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        task = progress.add_task("Analisi chunk", total=chunk_plan.total_chunks)

        for i, chunk in enumerate(chunk_plan.chunks, 1):
            progress.update(task, description=f"Chunk {i}: {chunk.module}")

            prompt = ANALYZE_CHUNK.format(
                project_name=config.project_name,
                static_analysis=static_analysis_text,
                chunk_content=chunk.to_text(),
            )

            try:
                response_text, in_tok, out_tok = call_fn(
                    client, config, prompt, max_output_tokens=4096,
                )
                chunk_analyses.append(
                    f"# Analisi modulo: {chunk.module}\n\n{response_text}"
                )
                total_input_tokens += in_tok
                total_output_tokens += out_tok
            except Exception as e:
                console.print(f"  [red]Errore nel chunk {i} ({chunk.module}): {e}[/red]")
                chunk_analyses.append(
                    f"# Analisi modulo: {chunk.module}\n\n"
                    f"[Analisi non disponibile — errore: {e}]"
                )

            progress.advance(task)

    # Combina tutte le analisi
    all_analyses = "\n\n---\n\n".join(chunk_analyses)

    # Budget per la sintesi: ~100K token di input
    synthesis_budget_chars = config.tokens_to_chars(100_000)
    all_analyses_truncated = smart_truncate(all_analyses, synthesis_budget_chars)

    # ── Fase 2: Documento funzionale ─────────────────────────────────────
    console.print("\n[bold cyan]Fase 2/3[/bold cyan] — Generazione documento funzionale\n")

    func_prompt = FUNCTIONAL_DOC.format(
        project_name=config.project_name,
        static_analysis=static_analysis_text,
        module_analyses=all_analyses_truncated,
    )

    functional_doc, in_tok, out_tok = call_fn(
        client, config, func_prompt, max_output_tokens=16384,
    )
    total_input_tokens += in_tok
    total_output_tokens += out_tok

    # ── Fase 3: Documento tecnico ────────────────────────────────────────
    console.print("\n[bold cyan]Fase 3/3[/bold cyan] — Generazione documento tecnico\n")

    tech_prompt = TECHNICAL_DOC.format(
        project_name=config.project_name,
        static_analysis=static_analysis_text,
        module_analyses=all_analyses_truncated,
    )

    technical_doc, in_tok, out_tok = call_fn(
        client, config, tech_prompt, max_output_tokens=16384,
    )
    total_input_tokens += in_tok
    total_output_tokens += out_tok

    # ── Riepilogo costi ──────────────────────────────────────────────────
    total_cost = config.estimate_cost(total_input_tokens, total_output_tokens)
    console.print(f"\n[bold green]Generazione completata![/bold green]")
    console.print(
        f"  Token totali: {total_input_tokens:,} input / "
        f"{total_output_tokens:,} output"
    )
    console.print(f"  Costo stimato: [bold]${total_cost:.4f}[/bold]")

    return functional_doc, technical_doc


def generate_documents_hybrid(
    module_chunk_plans: dict[str, ChunkPlan],
    analysis: ProjectAnalysis,
    config: DocGenConfig,
    call_fn: LlmCallFn | None = None,
) -> dict[str, tuple[str, str]]:
    """Genera documenti ibridi: per-microservizio + architettura di sistema.

    Fasi:
    1. Per ogni modulo: analisi chunk → doc funzionale + tecnica
    2. Genera riepilogo per modulo (per il doc di architettura)
    3. Genera documento di architettura di sistema

    Ritorna dict con chiave = nome modulo (+ "_sistema" per l'architettura),
    valore = (functional_md, technical_md).
    """
    if call_fn is None:
        client = Anthropic()
        call_fn = _call_claude
    else:
        client = None
    static_analysis_text = analysis.summary_text()

    total_input_tokens = 0
    total_output_tokens = 0

    results: dict[str, tuple[str, str]] = {}
    service_summaries: list[str] = []

    total_modules = len(module_chunk_plans)
    total_chunks_all = sum(p.total_chunks for p in module_chunk_plans.values())
    # Fasi: N chunks analisi + N moduli (func+tech = 2 call ciascuno) + N moduli summary + 1 architettura
    total_api_calls = total_chunks_all + (total_modules * 2) + total_modules + 1

    console.print(
        f"\n[bold cyan]Modalità ibrida[/bold cyan] — "
        f"{total_modules} microservizi, {total_chunks_all} chunk, "
        f"~{total_api_calls} chiamate API\n"
    )

    current_call = 0

    for mod_idx, (module_name, chunk_plan) in enumerate(sorted(module_chunk_plans.items()), 1):
        # Analisi statica filtrata per questo modulo (evita rumore cross-servizio)
        module_static_text = analysis.summary_text_for_module(module_name)

        console.print(
            f"\n[bold yellow]━━━ Microservizio {mod_idx}/{total_modules}: "
            f"{module_name} ({chunk_plan.total_chunks} chunk) ━━━[/bold yellow]\n"
        )

        # ── Fase 1: Analisi chunk per questo modulo ──────────────────
        chunk_analyses: list[str] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Analisi {module_name}", total=chunk_plan.total_chunks,
            )

            for i, chunk in enumerate(chunk_plan.chunks, 1):
                progress.update(task, description=f"Chunk {i}: {chunk.module}")

                prompt = ANALYZE_CHUNK.format(
                    project_name=config.project_name,
                    static_analysis=module_static_text,
                    chunk_content=chunk.to_text(),
                )

                try:
                    response_text, in_tok, out_tok = call_fn(
                        client, config, prompt, max_output_tokens=4096,
                    )
                    chunk_analyses.append(
                        f"# Analisi modulo: {chunk.module}\n\n{response_text}"
                    )
                    total_input_tokens += in_tok
                    total_output_tokens += out_tok
                except Exception as e:
                    console.print(f"  [red]Errore chunk {i}: {e}[/red]")
                    chunk_analyses.append(
                        f"# Analisi modulo: {chunk.module}\n\n"
                        f"[Analisi non disponibile — errore: {e}]"
                    )

                progress.advance(task)
                current_call += 1

        all_analyses = "\n\n---\n\n".join(chunk_analyses)
        synthesis_budget_chars = config.tokens_to_chars(100_000)
        all_analyses_truncated = smart_truncate(all_analyses, synthesis_budget_chars)

        # ── Fase 2: Doc funzionale per questo modulo ─────────────────
        console.print(f"  Generazione doc funzionale per {module_name}...")

        func_prompt = FUNCTIONAL_DOC.format(
            project_name=f"{config.project_name} — {module_name}",
            static_analysis=module_static_text,
            module_analyses=all_analyses_truncated,
        )

        functional_doc, in_tok, out_tok = call_fn(
            client, config, func_prompt, max_output_tokens=16384,
        )
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        current_call += 1

        # ── Fase 3: Doc tecnica per questo modulo ────────────────────
        console.print(f"  Generazione doc tecnica per {module_name}...")

        tech_prompt = TECHNICAL_DOC.format(
            project_name=f"{config.project_name} — {module_name}",
            static_analysis=module_static_text,
            module_analyses=all_analyses_truncated,
        )

        technical_doc, in_tok, out_tok = call_fn(
            client, config, tech_prompt, max_output_tokens=16384,
        )
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        current_call += 1

        results[module_name] = (functional_doc, technical_doc)

        # ── Riepilogo sintetico per architettura ─────────────────────
        console.print(f"  Generazione riepilogo {module_name}...")

        summary_prompt = SERVICE_SUMMARY.format(
            service_name=module_name,
            module_analyses=all_analyses_truncated,
        )

        summary_text, in_tok, out_tok = call_fn(
            client, config, summary_prompt, max_output_tokens=2048,
        )
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        current_call += 1

        service_summaries.append(f"### {module_name}\n\n{summary_text}")

        console.print(f"  [green]✓ {module_name} completato[/green]")

    # ── Fase finale: Documento di architettura di sistema ────────────
    console.print(
        f"\n[bold cyan]━━━ Generazione Documento di Architettura di Sistema ━━━[/bold cyan]\n"
    )

    all_summaries = "\n\n---\n\n".join(service_summaries)
    all_summaries_truncated = smart_truncate(all_summaries, synthesis_budget_chars)

    arch_prompt = SYSTEM_ARCHITECTURE_DOC.format(
        project_name=config.project_name,
        static_analysis=static_analysis_text,
        service_summaries=all_summaries_truncated,
    )

    architecture_doc, in_tok, out_tok = call_fn(
        client, config, arch_prompt, max_output_tokens=16384,
    )
    total_input_tokens += in_tok
    total_output_tokens += out_tok

    results["_architettura_sistema"] = (architecture_doc, "")

    # ── Riepilogo costi ──────────────────────────────────────────────
    total_cost = config.estimate_cost(total_input_tokens, total_output_tokens)
    console.print(f"\n[bold green]Generazione ibrida completata![/bold green]")
    console.print(
        f"  Token totali: {total_input_tokens:,} input / "
        f"{total_output_tokens:,} output"
    )
    console.print(f"  Costo stimato: [bold]${total_cost:.4f}[/bold]")

    return results
