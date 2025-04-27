import ast
import argparse
from pydantic_ai import Agent
from pydantic import BaseModel


class DocSuggestion(BaseModel):
    function_name: str
    full_docstring: str


sys_prompt = """
You are an expert Python assistant. 
Given a function write a concise PEP-257-style docstring for it.
Return only the docstring (including the triple-quotes).
"""

agent = Agent(
    "groq:llama-3.3-70b-versatile", output_type=DocSuggestion, system_prompt=sys_prompt
)


def extract_functions(source: str):
    tree = ast.parse(source)
    funcs = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            # only keep those without a docstring
            if ast.get_docstring(node) is None:
                # grab text from def ... through end_lineno
                lines = source.splitlines()[node.lineno - 1 : node.end_lineno]
                funcs.append("\n".join(lines))
    return funcs


def suggest_docstring(func_code: str) -> DocSuggestion:
    prompt = f"""
Here’s the function to document:

```python
{func_code}
```
"""
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

    with open("suggestions.txt", "w") as out:
        for fn in funcs:
            doc = suggest_docstring(fn)
            out.write(f"Function: {fn.split('(')[0]}\n")
            out.write(doc.full_docstring)
            out.write("\n\n")

    # suggestions = [suggest_docstring(fn) for fn in funcs]

    # with open(args.output, "w") as out:
    #     for s in suggestions:
    #         out.write(f"{s.full_docstring}\n\n")

    print(f"Generated {len(funcs)} suggestion(s) → {args.output}")


if __name__ == "__main__":
    main()
