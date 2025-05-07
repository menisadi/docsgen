#!/usr/bin/env python
import ast
import argparse
from pathlib import Path
from typing import Iterable

from pydantic_ai import Agent

from tqdm import tqdm


# Agent setup
SYS_PROMPT = (
    "You are an expert Python assistant.\n"
    "Given a function body, write a concise PEP‑257‑style docstring for it.\n"
    "Return *only* the docstring (including the triple‑quotes)."
)

agent = Agent(
    "groq:llama-3.3-70b-versatile",
    instructions=SYS_PROMPT,
    # NOTE: Later we can improve this (DocString type)
    output_type=str,
)


def extract_functions(source: str) -> tuple[list[str], int]:
    """Return list of *undocumented* function definitions and total count."""
    tree = ast.parse(source)
    funcs: list[str] = []
    total_funcs_count = 0
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            total_funcs_count += 1
            if ast.get_docstring(node) is None:
                lines = source.splitlines()[node.lineno - 1 : node.end_lineno]
                funcs.append("\n".join(lines))
    return funcs, total_funcs_count


def suggest_docstring(func_code: str) -> str:
    prompt = f"```python\n{func_code}\n```"
    return agent.run_sync(prompt).output


def iter_python_files(path: Path) -> Iterable[Path]:
    """Yield every *.py file under *path* (recursively if *path* is a dir)."""
    if path.is_file() and path.suffix == ".py":
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate docstring suggestions for Python functions."
    )
    parser.add_argument(
        "input_path",
        help="Python file or directory to scan recursively",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="suggestions.txt",
        help="Path where suggestions will be written",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    in_path = Path(args.input_path).expanduser().resolve()

    python_files = list(iter_python_files(in_path))
    if not python_files:
        print("No Python files found to process.")
        return

    total_missing = total_functions = 0
    with open(args.output, "w", encoding="utf-8") as out:
        for file in tqdm(python_files, desc="Scanning"):
            src = file.read_text(encoding="utf-8")
            funcs, func_count = extract_functions(src)
            total_functions += func_count
            total_missing += len(funcs)

            if not funcs:
                continue

            # Add the file name (without the path)
            out.write(f"# {file.relative_to(in_path.parent)}\n")
            for fn in funcs:
                doc = suggest_docstring(fn)
                # HACK: naive but works for defs
                fn_name = fn.split("(")[0][4:]
                out.write(f"Function: {fn_name}\n")
                out.write(doc)
                out.write("\n\n")

    if total_missing == 0:
        print("✨ All functions across all files already have docstrings!")
    else:
        print(
            f"Generated {total_missing} suggestion(s) "
            f"for {len(python_files)} file(s) → {args.output}"
        )


if __name__ == "__main__":
    main()
