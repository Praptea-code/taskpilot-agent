import ast
from pathlib import Path

BANNED = ("sales", "calendar", "email", "hubspot", "lead")


def docstring_nodes(tree: ast.AST) -> set[int]:
    result: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            result.add(id(first.value))
    return result


def banned_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    ignored = docstring_nodes(tree)
    hits: list[str] = []
    for node in ast.walk(tree):
        if id(node) in ignored:
            continue
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = node.value.lower()
        for word in BANNED:
            if word in text:
                hits.append(f"{path}:{node.lineno} contains {word}")
    return hits


def test_core_is_domain_blind() -> None:
    core = Path(__file__).resolve().parents[1] / "src" / "agent" / "core"
    hits: list[str] = []
    for path in sorted(core.rglob("*.py")):
        hits.extend(banned_strings(path))

    assert hits == [], "\n".join(hits)
