"""Guards against Python that the oldest supported version cannot read.

The scripts here promise Python 3.9 or later, and are developed on a newer one. These tests cannot stand in for a
run on 3.9, but they catch the two mistakes that were made: syntax that is too new, and type hints written with
"|", which 3.9 evaluates when it loads the file and then stops.

Run with:
  python -m unittest discover -s tests/tools
"""
import ast
import unittest
from pathlib import Path
from typing import Iterator, List

REPO = Path(__file__).resolve().parents[2]
OLDEST = (3, 9)


def python_files() -> List[Path]:
    return sorted(p for p in REPO.rglob("*.py") if ".git" not in p.parts and "__pycache__" not in p.parts)


def hints(tree: ast.AST) -> Iterator[ast.AST]:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]:
                if arg.annotation is not None:
                    yield arg.annotation
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


class PythonVersionsTest(unittest.TestCase):
    def test_every_script_is_readable_with_the_grammar_of_the_oldest_python(self) -> None:
        self.assertGreater(len(python_files()), 20)
        for path in python_files():
            with self.subTest(path=path.relative_to(REPO).as_posix()):
                ast.parse(path.read_text(encoding="utf-8"), feature_version=OLDEST)

    def test_type_hints_with_a_bar_are_only_used_where_python_keeps_hints_as_text(self) -> None:
        for path in python_files():
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            kept_as_text = any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
                               and any(a.name == "annotations" for a in n.names) for n in tree.body)
            if kept_as_text:
                continue
            bars = [h.lineno for h in hints(tree)
                    if any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr) for n in ast.walk(h))]
            with self.subTest(path=path.relative_to(REPO).as_posix()):
                self.assertEqual(bars, [], "these lines write a type hint with |, which Python 3.9 cannot load; add "
                                           "`from __future__ import annotations` at the top of the file")


if __name__ == "__main__":
    unittest.main()
