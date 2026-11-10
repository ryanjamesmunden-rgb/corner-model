"""Nothing evaluated at IMPORT time may name something defined further down the file.

THE BUG THIS IS NAMED AFTER. ValueSnapshotBody was written with
`days: int = BOT_VALUE_DAYS`, and that constant is defined several hundred lines below
it. A Pydantic class-body default is evaluated when the module is imported, so this was
a NameError on load — not a broken endpoint, the whole backend refusing to start. CI
reported 90 collection errors and 1040 passed instead of 1995.

IT CANNOT BE CAUGHT BY THE OTHER TESTS IN THIS DIRECTORY. The suites that run in this
container (bot_cards, odds_feed, value_send) never import server, because pymongo pulls
in cryptography and that panics here — so a clean local run says nothing whatsoever about
whether server.py can be imported at all. This reads the SOURCE instead, which works
everywhere, and it is the second time today an import-time name error reached a commit:
the first was `Dict[str, Any]` with Any absent from the typing import.

WHAT COUNTS AS IMPORT TIME. A class body and a module-level assignment both run on
import. A function body does not — it runs when called, by which point the whole module
exists — so a helper naming a constant defined below it is fine and is not reported.
"""
import ast
import os

SERVER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "server.py")


def _module_level_definitions(tree):
    """name -> the line it first becomes available on."""
    where = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            where.setdefault(node.name, node.lineno)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    where.setdefault(t.id, node.lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            where.setdefault(node.target.id, node.lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                where.setdefault((a.asname or a.name).split(".")[0], node.lineno)
    return where


def _forward_references(tree, defined):
    """(line, name) for every import-time expression naming a later definition."""
    bad = []

    def scan(expr, lineno, skip_names=()):
        if expr is None:
            return
        for n in ast.walk(expr):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                at = defined.get(n.id)
                if n.id in skip_names:
                    continue
                if at is not None and at > lineno:
                    bad.append((lineno, n.id, at))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            # Base classes, decorators and every default in the body run on import.
            for b in node.bases:
                scan(b, node.lineno)
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign):
                    scan(stmt.value, stmt.lineno)
                    scan(stmt.annotation, stmt.lineno)
                elif isinstance(stmt, ast.Assign):
                    scan(stmt.value, stmt.lineno)
        elif isinstance(node, ast.Assign):
            scan(node.value, node.lineno)
        elif isinstance(node, ast.AnnAssign):
            scan(node.value, node.lineno)
    return bad


def test_server_has_no_import_time_forward_references():
    tree = ast.parse(open(SERVER).read())
    defined = _module_level_definitions(tree)
    bad = _forward_references(tree, defined)
    assert not bad, (
        "these run when server.py is imported and name something defined later, which is "
        "a NameError on load and takes the whole backend down:\n"
        + "\n".join(f"  line {ln}: {name!r} is not defined until line {at}"
                    for ln, name, at in bad))


def test_the_check_would_have_caught_the_real_bug():
    """A guard that cannot fail is not a guard. This is the exact shape that shipped."""
    src = (
        "from pydantic import BaseModel\n"
        "class Body(BaseModel):\n"
        "    days: int = BOT_VALUE_DAYS\n"
        "BOT_VALUE_DAYS = 7\n"
    )
    tree = ast.parse(src)
    bad = _forward_references(tree, _module_level_definitions(tree))
    assert [(n, a) for _l, n, a in bad] == [("BOT_VALUE_DAYS", 4)]


def test_a_function_body_may_name_a_later_constant():
    """Function bodies run when called, by which point the module is fully built. Flagging
    those would make the check unusable — server.py is full of them by design."""
    src = (
        "def f():\n"
        "    return LATER\n"
        "LATER = 1\n"
    )
    tree = ast.parse(src)
    assert _forward_references(tree, _module_level_definitions(tree)) == []


def test_a_class_default_naming_an_earlier_constant_is_fine():
    src = (
        "EARLY = 3\n"
        "class Body:\n"
        "    days = EARLY\n"
    )
    tree = ast.parse(src)
    assert _forward_references(tree, _module_level_definitions(tree)) == []
