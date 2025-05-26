#!/usr/bin/env python
"""add_docstrings.py  –  Interactive docstring helper
====================================================

A single-file tool that can:

* **List** all Python functions that are missing a docstring (default).
  Uses the same concise report format as before.
* **Interactively** walk through those functions, optionally calling an LLM
  to propose a docstring and letting you accept, skip, edit, or regenerate.

Usage examples
--------------

```bash
# Just audit – print missing docstrings
python add_docstrings.py src/

# Save the audit to a file (non-interactive)
python add_docstrings.py src/ -r missing.txt

# Interactively step through each function
python add_docstrings.py src/ -i

# Show full function bodies (not just signature) while in -i mode
python add_docstrings.py src/ -i --show-body

# Be silent unless a problem is found (good for CI)
python add_docstrings.py src/ --quiet
```

Dependencies
~~~~~~~~~~~~
Only the **interactive** mode needs extra packages:

* ``pydantic_ai`` + an OpenAI-compatible backend for LLM generation.
* ``pygments`` (optional) for colourful syntax highlighting in the terminal.

The script will gracefully fall back if these are missing.
"""

from __future__ import annotations

import ast
import argparse
import sys
from pathlib import Path
from textwrap import indent
from typing import Iterable, NamedTuple, Optional

# ---------------------------------------------------------------------------
# Optional -- syntax highlighting support (Pygments)
# ---------------------------------------------------------------------------
try:
    from pygments import highlight
    from pygments.formatters import TerminalFormatter
    from pygments.lexers import PythonLexer

    def _highlight(code: str) -> str:  # pragma: no cover – cosmetic only
        return highlight(code, PythonLexer(), TerminalFormatter())

except ModuleNotFoundError:  # pragma: no cover

    def _highlight(code: str) -> str:  # type: ignore[override]
        return code


# ---------------------------------------------------------------------------
# Optional -- LLM support (pydantic_ai / OpenAI-compatible API)
# ---------------------------------------------------------------------------
try:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    _SYS_PROMPT = (
        "You are an expert Python assistant.\n"
        "Given a function body, write a concise PEP-257-style docstring for it.\n"
        "Return *only* the docstring (including the triple-quotes)."
    )

    _model = OpenAIModel(
        "phi3:mini",
        provider=OpenAIProvider(
            base_url="http://127.0.0.1:11434/v1",
            api_key="sk-local",  # any non-empty string
        ),
    )
    _agent = Agent(_model, instructions=_SYS_PROMPT, output_type=str)

    def _generate_docstring(fn_src: str) -> str:  # pragma: no cover – depends on LLM
        """Return a docstring suggestion from the model (may raise)."""
        prompt = f"```python\n{fn_src}\n```"
        return _agent.run_sync(prompt).output.strip()

except ModuleNotFoundError:  # pragma: no cover – LLM optional

    def _generate_docstring(fn_src: str) -> str:  # type: ignore[override]
        raise RuntimeError("LLM generation requested but pydantic_ai not installed")

# ---------------------------------------------------------------------------
# core datatypes
# ---------------------------------------------------------------------------


class Target(NamedTuple):
    """Information about a function that lacks a docstring."""

    filepath: Path
    lineno: int  # line number where the *def* appears (1-based)
    name: str  # function name
    src: str  # the full source of the function (for prompting)

    @property
    def signature(self) -> str:
        """Return the first line of *src* (i.e. the `def ...:` line)."""
        return self.src.splitlines()[0].rstrip()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def iter_python_files(path: Path) -> Iterable[Path]:
    """Yield every ``*.py`` file under *path* (recursively)."""
    if path.is_file() and path.suffix == ".py":
        yield path
    elif path.is_dir():
        yield from path.rglob("*.py")


def _extract_function_src(lines: list[str], node: ast.FunctionDef) -> str:
    """Return the source code (as a string) for *node* within *lines*."""
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def find_missing_docstrings(source: str, file_path: Path) -> list[Target]:
    """Return :class:`Target` objects for functions without docstrings."""
    tree = ast.parse(source)
    lines = source.splitlines()
    targets: list[Target] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and ast.get_docstring(node) is None:
            targets.append(
                Target(
                    filepath=file_path,
                    lineno=node.lineno,
                    name=node.name,
                    src=_extract_function_src(lines, node),
                )
            )
    # Sort for deterministic order within a file
    return sorted(targets, key=lambda t: t.lineno)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Audit or interactively add docstrings to Python files.",
    )
    p.add_argument(
        "input_path",
        help="File or directory to scan recursively for *.py files",
    )
    p.add_argument(
        "-r",
        "--report",
        metavar="PATH",
        help="Write the audit results to PATH in addition to any console output.",
    )
    p.add_argument(
        "-q",
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Suppress non-error console output (audit mode only).",
    )
    p.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Step through each missing docstring interactively.",
    )
    p.add_argument(
        "--show-body",
        action="store_true",
        help="In interactive mode, show the entire function body instead of just the signature.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# docstring insertion helper
# ---------------------------------------------------------------------------


def _insert_docstring(lines: list[str], tgt: Target, doc: str) -> None:
    """Insert *doc* under *tgt* in the list of *lines* (in-place)."""
    indent_spaces = " " * 4  # docstring one indent deeper than `def`
    indented = [
        indent_spaces + ln if i else indent_spaces + ln
        for i, ln in enumerate(doc.splitlines())
    ]
    insert_at = tgt.lineno  # 1-based index; we want to insert *after* def line
    lines[insert_at:insert_at] = indented + [""]  # blank line after docstring


# ---------------------------------------------------------------------------
# Interactive workflow
# ---------------------------------------------------------------------------


def _prompt(msg: str, valid: set[str]) -> str:  # pragma: no cover – I/O heavy
    """Prompt until the user enters a key in *valid* (case-insensitive)."""
    while True:
        ans = input(msg).strip().lower()
        if ans and ans[0] in valid:
            return ans[0]
        print(f"Please enter one of: {', '.join(sorted(valid))}.")


def _interactive_session(
    targets: list[Target], show_body: bool
) -> dict[Target, Optional[str]]:  # pragma: no cover
    """Return a mapping of Target -> accepted docstring (or None if skipped)."""
    results: dict[Target, Optional[str]] = {}

    for idx, tgt in enumerate(targets, 1):
        print("\n" + "=" * 80)
        print(f"[{idx}/{len(targets)}] {tgt.filepath}:{tgt.lineno}:{tgt.name}\n")
        code_snippet = tgt.src if show_body else tgt.signature
        print(_highlight(code_snippet))

        action = _prompt(
            "(g)enerate / (m)anual / (s)kip / (q)uit > ", {"g", "m", "s", "q"}
        )
        if action == "q":
            break
        if action == "s":
            results[tgt] = None
            continue

        if action == "m":
            print("Enter your docstring (end with an empty line):")
            lines: list[str] = []
            while True:
                ln = input()
                if ln.strip() == "":
                    break
                lines.append(ln)
            doc = "\n".join(lines).strip()
            if not (doc.startswith('"""') and doc.endswith('"""')):
                doc = f'"""\n{doc}\n"""'
            results[tgt] = doc
            continue

        # action == "g" – call LLM (with retry prompt)
        while True:
            try:
                doc = _generate_docstring(tgt.src)
            except Exception as e:  # noqa: BLE001  – show to user, ask next step
                print(f"\nError during generation: {e}\n")
                retry = _prompt("(r)etry / (s)kip / (q)uit > ", {"r", "s", "q"})
                if retry == "r":
                    continue
                if retry == "s":
                    doc = None  # type: ignore[assignment]
                    break
                return results  # early quit – nothing flushed yet
            else:
                print("\nSuggested docstring:\n" + indent(doc, "    "))
                choice = _prompt(
                    "(a)ccept / (r)egenerate / (e)dit / (s)kip / (q)uit > ",
                    {"a", "r", "e", "s", "q"},
                )
                if choice == "a":
                    results[tgt] = doc
                    break
                if choice == "e":
                    # allow inline editing
                    print("\nEdit the docstring (end with empty line):")
                    lines: list[str] = []
                    while True:
                        ln = input()
                        if ln.strip() == "":
                            break
                        lines.append(ln)
                    doc = "\n".join(lines).strip()
                    if not (doc.startswith('"""') and doc.endswith('"""')):
                        doc = f'"""\n{doc}\n"""'
                    results[tgt] = doc
                    break
                if choice == "s":
                    results[tgt] = None
                    break
                if choice == "q":
                    return results
                # else choice == "r" loop back to regenerate
    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:  # pragma: no cover – entry point
    args = _parse_args()
    root = Path(args.input_path).expanduser().resolve()

    py_files = list(iter_python_files(root))
    if not py_files:
        if not args.quiet:
            print("No *.py files found.")
        sys.exit(0)

    missing: list[Target] = []
    for file in py_files:
        src_text = file.read_text(encoding="utf-8")
        missing.extend(find_missing_docstrings(src_text, file))

    # ------------------------------------------------------------------
    # interactive mode
    # ------------------------------------------------------------------
    if args.interactive:
        if not missing:
            print("✨ No missing docstrings found.")
            sys.exit(0)

        accepted_map = _interactive_session(missing, args.show_body)
        if not accepted_map:
            print("No changes made.")
            sys.exit(0)

        # Insert docstrings back into files (honouring original order)
        grouped: dict[Path, list[tuple[Target, str]]] = {}
        for tgt, doc in accepted_map.items():
            if doc is None:
                continue  # skipped
            grouped.setdefault(tgt.filepath, []).append((tgt, doc))

        for path, td_list in grouped.items():
            src_lines = Path(path).read_text(encoding="utf-8").splitlines()
            # insert bottom-up so earlier insertions don’t shift later targets
            for tgt, doc in sorted(td_list, key=lambda p: p[0].lineno, reverse=True):
                _insert_docstring(src_lines, tgt, doc)
            Path(path).write_text("\n".join(src_lines) + "\n", encoding="utf-8")
            print(f"✏️  Updated {path} (+{len(td_list)} docstring(s))")
        print("✅ All accepted docstrings inserted.")
        return

    # ------------------------------------------------------------------
    # non-interactive audit mode (default)
    # ------------------------------------------------------------------
    if not missing:
        if not args.quiet:
            print("✨ No missing docstrings found.")
        sys.exit(0)

    # Sort for deterministic output: by file, then line
    missing.sort(key=lambda t: (t.filepath, t.lineno))

    lines = [f"{t.filepath.relative_to(root)}:{t.lineno}:{t.name}" for t in missing]

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if not args.quiet:
            print(
                f"✅ Report written to {report_path} ({len(lines)} missing docstring(s))."
            )

    if not args.quiet:
        print("\n".join(lines))

    # Non-zero exit status signals problems (useful for CI)
    sys.exit(1)


if __name__ == "__main__":
    main()
