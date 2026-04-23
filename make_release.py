#!/usr/bin/env python3
"""Crea uno zip di release con solo i file necessari per l'installazione."""

import os
import zipfile
import tomllib  # Python 3.11+
from pathlib import Path

# Root del progetto
PROJECT_ROOT = Path(__file__).parent

# Nome cartella dentro lo zip
FOLDER_NAME = "ai-doc-generator"

# File e cartelle da includere
INCLUDE = [
    "docgen/",          # Package Python
    "templates/",       # Template DOCX aziendale (richiesto da --render)
    "GUIDA_UTENTE.md",
    "README.md",
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
]

# Directory di output
RELEASE_DIR = PROJECT_ROOT / "release"

def get_version() -> str:
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def main() -> None:
    RELEASE_DIR.mkdir(exist_ok=True)

    version = get_version()
    zip_name = f"docgen_{version}.zip"
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
