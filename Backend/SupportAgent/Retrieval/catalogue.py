from SupportAgent.config import KB_DIR

CATALOG_FILE = "Catalog.md"

def load_catalogue() -> str:
    return (KB_DIR / CATALOG_FILE).read_text(encoding="utf-8")

def list_md_files() -> set[str]:
    return {p.name for p in KB_DIR.glob("*.md") if p.name != CATALOG_FILE}

def read_md_file(name: str) -> str:
    valid = list_md_files()
    if name not in valid:                      # exact-match allowlist, so no path traversal
        raise ValueError(f"Unknown file '{name}'. Valid files: {sorted(valid)}")
    text = (KB_DIR / name).read_text(encoding="utf-8")
    return text