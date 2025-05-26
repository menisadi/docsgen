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

## Installation

```bash
pip install docgaps            # base install
pip install docgaps[highlight] # + colourised code in the TTY
pip install docgaps[llm]       # + LLM support (pydantic-ai)
```

> The `[llm]` extra expects an OpenAI-compatible endpoint. See the
> _Environment_ section below.

---

## Quick start

Audit the current project and open an interactive session for every missing
docstring:

```bash
docgaps -i src/
```

Generate a plain report (useful for CI) and fail the build if any gaps are
found:

```bash
# exit-code 1 when gaps exist
docgaps src/ > docgap-report.txt
```

---

## Environment variables

| Variable          | Purpose                                             | Example                     |
| ----------------- | --------------------------------------------------- | --------------------------- |
| `EDITOR`          | Command launched for manual edits                   | `nvim`, `code -w`           |
| `OPENAI_API_KEY`  | Any non-empty string for local Ollama-style servers | `sk-local`                  |
| `OPENAI_BASE_URL` | Override the default `http://127.0.0.1:11434/v1`    | `https://api.openai.com/v1` |
