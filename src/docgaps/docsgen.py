#!/usr/bin/env python
"""add_docstrings.py  –  Interactive docstring helper
====================================================

A single‑file tool that can audit or add docstrings and now **lets you edit
in your preferred $EDITOR** when you choose *edit* (or *manual*) in the
interactive flow.

Usage examples
~~~~~~~~~~~~~~
```
export EDITOR="nvim"               # once per shell
python add_docstrings.py src/ -i   # choose (e)dit ➜ opens Neovim
```

All previous flags (**‑q/‑‑quiet**, **‑r/‑‑report**, **‑‑show‑body** …) work the
same.
"""

import ast
import argparse
import os
import re

import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import indent
from typing import Iterable, NamedTuple, Optional

# ---------------------------------------------------------------------------
# Optional ‑‑ syntax highlighting support (Pygments)
# ---------------------------------------------------------------------------
try:
    from pygments import highlight
    from pygments.formatters import TerminalFormatter
    from pygments.lexers import PythonLexer

    def _highlight(code: str) -> str:  # pragma: no cover – cosmetic only
        return highlight(code, PythonLexer(), TerminalFormatter())

except ModuleNotFoundError:  # pragma: no cover – pygments optional

    def _highlight(code: str) -> str:  # type: ignore[override]
        return code


# ---------------------------------------------------------------------------
# Optional ‑‑ LLM support (pydantic_ai / OpenAI‑compatible API)
# ---------------------------------------------------------------------------
try:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    _SYS_PROMPT = (
        "You are an expert Python assistant.\n"
        "Given a function body, write a concise PEP‑257‑style docstring for it.\n"
        "Return *only* the docstring (including the triple‑quotes)."
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
    lineno: int  # line number where the *def* appears (1‑based)
    name: str  # function name
    src: str  # the full source of the function (for prompting)

    @property
    def signature(self) -> str:
        """
        Return the complete `def …:` header, even if it spans
        multiple lines or follows decorators/blank lines.
        """
        lines = self.src.splitlines()
        sig_lines: list[str] = []

        # skip leading blank lines and decorators
        it = iter(lines)
        for line in it:
            if re.match(r"\s*(async\s+)?def\b", line):
                sig_lines.append(line.rstrip())
                break

        # grab subsequent lines until the header ends with ':'
        for line in it:
            sig_lines.append(line.rstrip())
            if line.rstrip().endswith(":"):
                break

        if not sig_lines:
            raise ValueError("No function header found in src")

        return "\n".join(sig_lines)


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
    """
    Return Target objects for functions that lack a docstring.

    Files that raise a SyntaxError (stub files, partially-checked-out code,
    or code written for a newer Python than the running interpreter) are
    skipped silently so the scan can continue.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:  # ← NEW: keep the audit alive
        return []

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
    return sorted(targets, key=lambda t: t.lineno)  # deterministic


# ---------------------------------------------------------------------------
# CLI parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Audit or interactively add docstrings to Python files.",
    )
    p.add_argument(
        "input_path", help="File or directory to scan recursively for *.py files"
    )
    p.add_argument(
        "-r",
        "--report",
        metavar="PATH",
        help="Write the audit results to PATH as well.",
    )
    p.add_argument(
        "-q",
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Suppress audit console output.",
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
        help="Show full function bodies instead of signatures in -i mode.",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# $EDITOR integration
# ---------------------------------------------------------------------------


def _edit_with_editor(
    initial: str = "",
) -> Optional[str]:  # pragma: no cover – I/O heavy
    """Open $EDITOR with *initial* text and return the edited content (or None)."""
    editor = os.environ.get("EDITOR")
    if not editor:
        return None

    # Create a named temporary file that persists after closing
    fd, path = tempfile.mkstemp(suffix=".tmp", text=True)
    os.close(fd)  # we will reopen with normal file API
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(initial)
        try:
            subprocess.run(shlex.split(editor) + [path], check=True)
        except Exception as exc:  # editor failed / user cancelled
            print(f"Editor launch failed: {exc}. Falling back to inline input.")
            return None
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return content.strip()
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _inline_multiline(
    prompt_msg: str, initial: str = ""
) -> str:  # pragma: no cover – I/O heavy
    """Gather multi‑line input from stdin until an empty line."""
    print(prompt_msg)
    if initial:
        print(
            "(Current text shown below; edit as needed, then press ENTER on a blank line)"
        )
        for ln in initial.splitlines():
            print(ln)
    lines: list[str] = []
    while True:
        ln = input()
        if ln.strip() == "":
            break
        lines.append(ln)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# docstring insertion helper
# ---------------------------------------------------------------------------


def _insert_docstring(lines: list[str], tgt: Target, doc: str) -> None:
    """
    Insert *doc* directly under *tgt* inside *lines* (in-place).

    The docstring is indented one level deeper than the *def* line so it
    matches PEP-8/black expectations for function bodies inside any nesting
    level (modules, classes, or nested functions).
    """
    def_line = lines[tgt.lineno - 1]
    base_indent = def_line[: len(def_line) - len(def_line.lstrip())]  # leading ws
    indent_spaces = base_indent + " " * 4  # one extra level

    indented = [indent_spaces + ln for ln in doc.splitlines()]
    insert_at = tgt.lineno  # after the def
    lines[insert_at:insert_at] = indented + [""]  # keep blank line


# ---------------------------------------------------------------------------
# Interactive workflow
# ---------------------------------------------------------------------------


def _prompt(msg: str, valid: set[str]) -> str:  # pragma: no cover – I/O heavy
    """Prompt until the user enters a key in *valid* (case‑insensitive)."""
    while True:
        ans = input(msg).strip().lower()
        if ans and ans[0] in valid:
            return ans[0]
        print(f"Please enter one of: {', '.join(sorted(valid))}.")


def _edit_docstring(initial: str = "") -> str:  # pragma: no cover – I/O heavy
    """Let the user edit *initial* using $EDITOR or inline fallback."""
    edited = _edit_with_editor(initial)
    if edited is None:  # fallback to inline
        edited = _inline_multiline("Enter docstring (end with empty line):", initial)
    # Wrap with triple quotes if not already present
    if not (edited.startswith('"""') and edited.endswith('"""')):
        edited = f'"""\n{edited}\n"""'
    return edited


def _interactive_session(
    targets: list[Target], show_body: bool
) -> dict[Target, Optional[str]]:  # pragma: no cover – I/O heavy
    """Walk through *targets* and return mapping of accepted docstrings."""
    results: dict[Target, Optional[str]] = {}

    for idx, tgt in enumerate(targets, 1):
        print("\n" + "=" * 80)
        print(f"[{idx}/{len(targets)}] {tgt.filepath}:{tgt.lineno}:{tgt.name}\n")
        snippet = tgt.src if show_body else tgt.signature
        print(_highlight(snippet))

        action = _prompt(
            "(g)enerate / (m)anual / (s)kip / (q)uit > ", {"g", "m", "s", "q"}
        )
        if action == "q":
            break
        if action == "s":
            results[tgt] = None
            continue

        if action == "m":  # manual editing from scratch
            doc = _edit_docstring()
            results[tgt] = doc
            continue

        # action == "g" – generate first, then review/edit
        while True:
            try:
                suggestion = _generate_docstring(tgt.src)
            except Exception as e:  # noqa: BLE001
                print(f"\nError during generation: {e}\n")
                retry = _prompt("(r)etry / (s)kip / (q)uit > ", {"r", "s", "q"})
                if retry == "r":
                    continue
                if retry == "s":
                    suggestion = None  # type: ignore[assignment]
                    break
                return results
            else:
                print("\nSuggested docstring:\n" + indent(suggestion, "    "))
                choice = _prompt(
                    "(a)ccept / (r)egenerate / (e)dit / (s)kip / (q)uit > ",
                    {"a", "r", "e", "s", "q"},
                )
                if choice == "a":
                    results[tgt] = suggestion
                    break
                if choice == "e":
                    edited = _edit_docstring(suggestion)
                    results[tgt] = edited
                    break
                if choice == "s":
                    results[tgt] = None
                    break
                if choice == "q":
                    return results
                # else "r" – regenerate
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
