import re
import sys
from pathlib import Path

DOCS = Path("docs/code")
LINK = re.compile(r"\[([^\]]+)\]\((\.\./\.\./[^)#]+)(?:#L(\d+))?\)")
SYMBOL = re.compile(r"`([^`]+)`")


def symbol_name(link_text: str) -> str | None:
    match = SYMBOL.search(link_text)
    if match is None:
        return None
    return match.group(1).split("(")[0].split(".")[-1].strip()


def problems_in(document: Path) -> list[str]:
    problems = []
    for text, relative, line in LINK.findall(document.read_text()):
        target = (document.parent / relative).resolve()
        if not target.exists():
            problems.append(f"{document}: missing file {relative}")
            continue
        name = symbol_name(text)
        if not line or name is None:
            continue
        lines = target.read_text().splitlines()
        number = int(line)
        if number > len(lines) or name not in lines[number - 1]:
            problems.append(f"{document}: `{name}` is not on line {number} of {relative}")
    return problems


def main() -> int:
    problems = [problem for doc in sorted(DOCS.glob("*.md")) for problem in problems_in(doc)]
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
