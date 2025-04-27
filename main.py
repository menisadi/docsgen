import ast
import argparse
from typing import List, Optional
from pydantic import BaseModel
from pydantic_ai import Agent


class ParamDoc(BaseModel):
    name: str
    type: str
    desc: str


class DocSuggestion(BaseModel):
    name: str
    summary: str
    description: Optional[str]
    params: List[ParamDoc]
    returns: str
    full_docstring: str


agent = Agent(
    "groq:llama-3.3-70b-versatile",
    output_type=DocSuggestion,
    system_prompt="""
You are a Python assistant.
Given a single top-level function body (no surrounding code), return
ONLY valid JSON matching this schema:

{
  "name": "<function name>",
  "summary": "<one-line summary>",
  "description": "<longer description or null>",
  "params": [
    {"name": "<param1>", "type": "<type1>", "desc": "<desc1>"},
    ...
  ],
  "returns": "<return description>",
  "full_docstring": "<the entire triple-quoted docstring>"
}
""",
)


def extract_functions(source: str) -> List[str]:
    """
    Parse the source and return each top-level function without a docstring.
    """
    tree = ast.parse(source)
    missing = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and ast.get_docstring(node) is None:
            snippet = "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno])
            missing.append(snippet)
    return missing


def suggest_docstring(func_code: str) -> DocSuggestion:
    """
    Ask the agent for a structured docstring suggestion.
    """
    prompt = f"""
Here’s the function to document:

```python
{func_code}
```

Emit ONLY the JSON described in the system prompt—no extra text.
"""
    result = agent.run_sync(prompt)
    return result.output


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate structured docstring suggestions for Python functions."
    )
    parser.add_argument(
        "input_file",
        help="Path to the Python source file to scan",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write suggestions",
        default="suggestions.txt",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.input_file, "r") as f:
        src = f.read()
    funcs = extract_functions(src)
    if not funcs:
        print("✔️ All functions already have docstrings!")
        return

    suggestions = [suggest_docstring(fn) for fn in funcs]

    with open(args.output, "w") as out:
        for s in suggestions:
            out.write(f"{s.full_docstring}\n\n")

    print(f"Generated {len(suggestions)} suggestion(s) → {args.output}")


if __name__ == "__main__":
    main()
