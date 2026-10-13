from pathlib import Path


def is_halted(halt_file: Path) -> bool:
    return halt_file.exists()
