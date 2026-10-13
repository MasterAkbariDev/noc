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


def definition_line(lines: list[str], name: str) -> int | None:
    pattern = re.compile(
        rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(name)}\b|^{re.escape(name)}\s*[:=]"
    )
    found = [index + 1 for index, line in enumerate(lines) if pattern.search(line)]
    return found[0] if len(found) == 1 else None


def check(document: Path, fix: bool) -> list[str]:
    text = document.read_text()
    problems: list[str] = []

    def review(match: re.Match[str]) -> str:
        link_text, relative, line = match.groups()
        target = (document.parent / relative).resolve()
        if not target.exists():
            problems.append(f"{document}: missing file {relative}")
            return match.group(0)
        name = symbol_name(link_text)
        if not line or name is None:
            return match.group(0)
        lines = target.read_text().splitlines()
        number = int(line)
        if number <= len(lines) and name in lines[number - 1]:
            return match.group(0)
        moved_to = definition_line(lines, name) if fix else None
        if moved_to is None:
            problems.append(f"{document}: `{name}` is not on line {number} of {relative}")
            return match.group(0)
        new_text = link_text.replace(f"L{number}", f"L{moved_to}")
        return f"[{new_text}]({relative}#L{moved_to})"

    updated = LINK.sub(review, text)
    if fix and updated != text:
        document.write_text(updated)
    return problems


def main() -> int:
    fix = "--fix" in sys.argv[1:]
    problems = [problem for doc in sorted(DOCS.glob("*.md")) for problem in check(doc, fix)]
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
