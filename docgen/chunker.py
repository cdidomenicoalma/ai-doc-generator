"""Chunker — raggruppa file per modulo rispettando il budget token."""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import DocGenConfig, CHARS_PER_TOKEN
from .scanner import ScanResult, ScannedFile


@dataclass
class Chunk:
    """Un gruppo di file che sta nel budget token per una singola chiamata LLM."""

    module: str                              # Nome modulo logico
    files: list[ScannedFile] = field(default_factory=list)
    total_chars: int = 0
    total_tokens_est: int = 0

    def add_file(self, file: ScannedFile) -> None:
        """Aggiunge un file al chunk aggiornando i contatori."""
        self.files.append(file)
        chars = len(file.content)
        self.total_chars += chars
        self.total_tokens_est = int(self.total_chars / CHARS_PER_TOKEN)

    def to_text(self) -> str:
        """Serializza il chunk in testo per il prompt LLM."""
        parts: list[str] = []
        parts.append(f"# Modulo: {self.module}")
        parts.append(f"File inclusi: {len(self.files)}")
        parts.append(f"Token stimati: ~{self.total_tokens_est:,}")
        parts.append("")

        for f in self.files:
            parts.append(f"## File: {f.path}")
            parts.append(f"Categoria: {f.category} | Priorità: {f.priority}")
            if f.truncated:
                parts.append("[CONTENUTO TRONCATO]")
            parts.append(f"```{f.extension.lstrip('.')}")
            parts.append(f.content)
            parts.append("```")
            parts.append("")

        return "\n".join(parts)


@dataclass
class ChunkPlan:
    """Piano completo dei chunk con stime di costo."""

    chunks: list[Chunk] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)

    @property
    def total_files(self) -> int:
        return sum(len(c.files) for c in self.chunks)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.total_tokens_est for c in self.chunks)

    def estimate_total_cost(self, analysis_tokens: int = 0) -> float:
        """Stima il costo totale includendo le 3 fasi.
        Fase 1: N chunk di analisi (~3.5K output ciascuno)
        Fase 2: Sintesi funzionale (~8K output)
        Fase 3: Sintesi tecnica (~8K output)
        
        analysis_tokens: stima token dell'analisi statica (inviata come contesto).
        """
        call_overhead = 500
        static_tokens = analysis_tokens if analysis_tokens > 0 else 5000

        # Fase 1: input = chunk content + static_analysis + prompt overhead
        phase1_input = self.total_input_tokens + (self.total_chunks * (static_tokens + 3000 + call_overhead))
        phase1_output = self.total_chunks * 4000  # Claude usa ~95% di max_output_tokens=4096

        # Fase 2-3: input = analisi aggregate (troncate a ~100K) + analisi statica + prompt
        synthesis_input = min(phase1_output, 100_000) + static_tokens + 3000 + call_overhead
        phase23_output = 16000

        total_input = phase1_input + synthesis_input * 2
        total_output = phase1_output + phase23_output

        from .config import COST_INPUT_PER_M, COST_OUTPUT_PER_M
        return (
            (total_input / 1_000_000) * COST_INPUT_PER_M
            + (total_output / 1_000_000) * COST_OUTPUT_PER_M
        )


def create_chunks(scan_result: ScanResult, config: DocGenConfig) -> ChunkPlan:
    """Crea i chunk raggruppando i file per modulo, rispettando il budget token.

    I file business_critical hanno priorità alta e vengono sempre inclusi.
    Se non entrano nei chunk principali, viene creato un chunk dedicato
    "cross-cutting" per il modulo.
    """
    plan = ChunkPlan()
    budget_chars = config.tokens_to_chars(config.chunk_budget)

    # Raggruppa file per modulo
    by_module = scan_result.files_by_module()

    for module_name in sorted(by_module.keys()):
        files = by_module[module_name]

        # Ordina per priorità (alta prima), poi per path
        priority_order = {"alta": 0, "media": 1, "bassa": 2}
        files.sort(key=lambda f: (priority_order.get(f.priority, 2), f.path))

        current_chunk = Chunk(module=module_name)
        overflow_critical: list[ScannedFile] = []

        for file in files:
            file_chars = len(file.content)

            # File singolo che supera il budget → chunk dedicato
            if file_chars > budget_chars:
                # Salva chunk corrente se ha file
                if current_chunk.files:
                    plan.chunks.append(current_chunk)
                    current_chunk = Chunk(module=module_name)

                dedicated = Chunk(module=f"{module_name} (file grande)")
                dedicated.add_file(file)
                plan.chunks.append(dedicated)
                continue

            # Se aggiungere il file sfora il budget, chiudi chunk corrente
            if current_chunk.total_chars + file_chars > budget_chars:
                if current_chunk.files:
                    plan.chunks.append(current_chunk)
                current_chunk = Chunk(module=module_name)

                # Se il file è business_critical e non entra neanche in un chunk vuoto
                # (impossibile dato il check sopra), lo mettiamo in overflow
                if file.category == "business_critical" and file_chars > budget_chars:
                    overflow_critical.append(file)
                    continue

            current_chunk.add_file(file)

        # Aggiungi ultimo chunk se ha file
        if current_chunk.files:
            plan.chunks.append(current_chunk)

        # Se ci sono file business_critical in overflow, crea chunk cross-cutting
        if overflow_critical:
            cross_chunk = Chunk(module=f"{module_name} (cross-cutting)")
            for f in overflow_critical:
                cross_chunk.add_file(f)
            plan.chunks.append(cross_chunk)

    return plan
