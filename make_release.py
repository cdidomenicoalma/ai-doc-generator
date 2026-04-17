#!/usr/bin/env python3
"""Crea uno zip di release con solo i file necessari per l'installazione."""

import os
import zipfile
from datetime import datetime
from pathlib import Path

# Root del progetto
PROJECT_ROOT = Path(__file__).parent

# Nome cartella dentro lo zip
FOLDER_NAME = "ai-doc-generator"

# File e cartelle da includere
INCLUDE = [
    "docgen/",          # Package Python
    "GUIDA_UTENTE.md",
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
]

# Directory di output
RELEASE_DIR = PROJECT_ROOT / "release"


def main() -> None:
    RELEASE_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    zip_name = f"docgen_{timestamp}.zip"
    zip_path = RELEASE_DIR / zip_name

    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in INCLUDE:
            src = PROJECT_ROOT / entry

            if src.is_dir():
                # Aggiungi tutti i file della directory (escludi __pycache__)
                for root, dirs, files in os.walk(src):
                    dirs[:] = [d for d in dirs if d != "__pycache__"]
                    for fname in files:
                        fpath = Path(root) / fname
                        arcname = f"{FOLDER_NAME}/{fpath.relative_to(PROJECT_ROOT)}"
                        zf.write(fpath, arcname)
                        count += 1
            elif src.is_file():
                arcname = f"{FOLDER_NAME}/{src.relative_to(PROJECT_ROOT)}"
                zf.write(src, arcname)
                count += 1
            else:
                print(f"  ⚠ Non trovato: {entry}")

    size_kb = zip_path.stat().st_size / 1024
    print(f"✅ Release creata: {zip_path}")
    print(f"   {count} file, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
