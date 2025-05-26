# docgaps — mind the docstring gap!

`docgaps` scans your Python codebase for functions that **lack a docstring** and lets you
insert one on the spot – by hand or via an LLM – right from your terminal.

---

## Features

- **Audit** an entire project in seconds – shows file + line for each gap.
- **Interactive fix-up** (`-i`) with:
    - Manual editor launch (respects `$EDITOR`).
    - Automatic docstring suggestion via an OpenAI-compatible LLM.
- Pure-Python, no database, no network calls (unless you ask for LLM help).
- Requires **Python ≥ 3.8**.

---

```bash
docgaps -i src/
```
