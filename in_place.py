#!/usr/bin/env python
import ast
import argparse
from pathlib import Path
from typing import Iterable, NamedTuple

from tqdm import tqdm
from pydantic_ai import Agent

_SYS_PROMPT = (
    "You are an expert Python assistant.\n"
    "Given a function body, write a concise PEP‑257‑style docstring for it.\n"
    "Return *only* the docstring (including the triple‑quotes)."
)

agent = Agent(
    "groq:llama-3.3-70b-versatile",
    instructions=_SYS_PROMPT,
    output_type=str,
)


class Target(NamedTuple):
    lineno: int  # line **after** which to insert the docstring
    col: int  # indentation of the `def`
    src: str  # source of the whole function (for the LLM)
    name: str  # function name


def find_targets(source: str) -> list[Target]:
    """Return every function that is missing a docstring."""
    tree = ast.parse(source)
    lines = source.splitlines()
    targets: list[Target] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and ast.get_docstring(node) is None:
            # Extract the raw source of the function (node.lineno is 1‑based)
            fn_src = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            targets.append(
                Target(
                    lineno=node.lineno,  # insert AFTER def line
                    col=node.col_offset,
                    src=fn_src,
                    name=node.name,
                )
            )
    # Insert bottom‑up so earlier inserts don't shift later positions
    return sorted(targets, key=lambda t: t.lineno, reverse=True)


def insert_docstring(lines: list[str], tgt: Target, doc: str) -> None:
    """Mutate *lines* in‑place, inserting *doc* under the given target."""
    indented_doc = []
    indent = " " * (tgt.col + 4)  # one level deeper than the `def`
    for i, ln in enumerate(doc.splitlines()):
        # keep triple‑quotes exactly as produced, just indent
        indented_doc.append(f"{indent}{ln}" if i > 0 else f"{indent}{ln}")
    # lineno is 1‑based; we want to insert *after* that line
    insert_at = tgt.lineno
    lines[insert_at:insert_at] = indented_doc + [""]  # blank line after doc


def iter_python_files(path: Path) -> Iterable[Path]:
    if path.is_file() and path.suffix == ".py":
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Add missing docstrings to Python files in‑place."
    )
    p.add_argument("input_path", help="File or directory to scan recursively")
    p.add_argument(
        "-r",
        "--report",
        default="docstring_report.txt",
        help="Write a summary report here",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.input_path).expanduser().resolve()

    py_files = list(iter_python_files(root))
    if not py_files:
        print("No *.py files found.")
        return

    report_lines: list[str] = []
    total_added = 0

    for file in tqdm(py_files, desc="Processing"):
        src_text = file.read_text(encoding="utf-8")
        targets = find_targets(src_text)

        if not targets:
            continue  # nothing missing

        lines = src_text.splitlines()
        for tgt in targets:
            prompt = f"```python\n{tgt.src}\n```"
            doc = agent.run_sync(prompt).output.strip()
            insert_docstring(lines, tgt, doc)
            total_added += 1
            rel = file.relative_to(root.parent)
            report_lines.append(f"{rel}:{tgt.name}")

        file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # ── final messages ────────────────────────────────────────────────
    if total_added == 0:
        print("✨ All functions already documented.")
    else:
        report_path = Path(args.report).expanduser().resolve()
        report_path.write_text(
            f"Added {total_added} docstring(s) to {len(py_files)} file(s):\n"
            + "\n".join(report_lines)
            + "\n",
            encoding="utf-8",
        )
        print(f"✅ Inserted {total_added} docstring(s). See → {report_path}")


if __name__ == "__main__":
    main()
