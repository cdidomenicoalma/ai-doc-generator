"""Modalità operative di DocGen.

Aggiungere nuove modalità qui e implementare i relativi generatori in main.py.
"""
from __future__ import annotations

# Costanti modalità
DOCS = "docs"
TESTS = "tests"

# Registry: mode → etichetta leggibile
AVAILABLE_MODES: dict[str, str] = {
    DOCS: "Documentazione (specifica funzionale + tecnica)",
    TESTS: "Analisi di test (documento markdown di test)",
}
