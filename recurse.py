#!/usr/bin/env python
import ast
import argparse
from pathlib import Path
from typing import Iterable

from pydantic_ai import Agent
from pydantic import BaseModel

from tqdm import tqdm


class DocSuggestion(BaseModel):
    function_name: str
    full_docstring: str


SYS_PROMPT = """
You are an expert Python assistant. 
Given a function, write a concise PEP-257-style docstring for it.
Return only the docstring (including the triple-quotes).
"""

agent = Agent(
    "groq:llama-3.3-70b-versatile",
    output_type=DocSuggestion,
    system_prompt=SYS_PROMPT,
)


def extract_functions(source: str) -> tuple[list[str], int]:
    tree = ast.parse(source)
    funcs, total_funcs_count = [], 0
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            total_funcs_count += 1
            if ast.get_docstring(node) is None:
                lines = source.splitlines()[node.lineno - 1 : node.end_lineno]
                funcs.append("\n".join(lines))
    return funcs, total_funcs_count


def suggest_docstring(func_code: str) -> DocSuggestion:
    prompt = f"""
Write a concise PEP-257-style docstring for the following Python function.  
Return only the docstring (including the triple-quotes).

```python
{func_code}
```
Emit ONLY the answer described in the system prompt—no extra text.
"""
    result = agent.run_sync(prompt)
    return result.output


def iter_python_files(path: Path) -> Iterable[Path]:
    """Yield every *.py file under *path* (recursively if path is a dir)."""
    if path.is_file() and path.suffix == ".py":
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate structured docstring suggestions for Python functions."
    )
    parser.add_argument(
        "input_path",
        help="Path to a Python source file *or* a directory to scan recursively",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="suggestions.txt",
        help="Where to write all docstring suggestions",
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
        for i, file in enumerate(python_files):
            try:
                src = file.read_text(encoding="utf-8")
                funcs, func_count = extract_functions(src)
            except Exception:
                raise IOError(
                    f"Problem with reading and extracting the functions from file {i}."
                )
            total_functions += func_count
            total_missing += len(funcs)

            if not funcs:
                continue

            out.write(f"# {file.relative_to(in_path.parent)}\n")
            try:
                for fn in funcs:
                    doc = suggest_docstring(fn)
                    out.write(f"Function: {fn.split('(')[0][4:]}\n")
                    out.write(doc.full_docstring)
                    out.write("\n\n")
            except Exception:
                raise Exception(f"Problem with generating docs for file {i}")

    if total_missing == 0:
        print("✨ All functions across all files already have docstrings!")
    else:
        print(
            f"Generated {total_missing} suggestion(s) "
            f"for {len(python_files)} file(s) → {args.output}"
        )


if __name__ == "__main__":
    main()
