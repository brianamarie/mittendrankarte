"""Fill en.md from de.md using Argos Translate when installed."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / "articles"


def ensure_de_en() -> None:
    import argostranslate.package

    installed = argostranslate.package.get_installed_packages()
    if any(p.from_code == "de" and p.to_code == "en" for p in installed):
        return
    argostranslate.package.update_package_index()
    available = argostranslate.package.get_available_packages()
    pkg = next(p for p in available if p.from_code == "de" and p.to_code == "en")
    argostranslate.package.install_from_path(pkg.download())


def main() -> None:
    try:
        import argostranslate.translate
    except ImportError:
        raise SystemExit("pip install argostranslate  (optional)")
    ensure_de_en()
    for folder in sorted(path.parent for path in ARTICLES.rglob("de.md")):
        de = folder / "de.md"
        en = folder / "en.md"
        if not de.exists():
            continue
        if en.exists() and en.stat().st_size > 0:
            print(f"skip {folder.name} (en.md already there)")
            continue
        text = de.read_text(encoding="utf-8")
        out = argostranslate.translate.translate(text, "de", "en")
        en.write_text(out.strip() + "\n", encoding="utf-8")
        print(f"wrote {en}")


if __name__ == "__main__":
    main()
