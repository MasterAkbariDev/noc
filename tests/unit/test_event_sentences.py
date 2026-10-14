import ast
from pathlib import Path

from noc.reporting import plain_language as words

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "noc" / "src" / "noc"
ADD_EVENT = "add_event"
EVENT_TYPE_POSITION = 2


def module_string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Constant):
            value = statement.value.value
            if isinstance(value, str):
                constants.update(
                    {
                        target.id: value
                        for target in statement.targets
                        if isinstance(target, ast.Name)
                    }
                )
    return constants


def called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def event_type_of(argument: ast.expr, constants: dict[str, str]) -> str:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value
    if isinstance(argument, ast.Name) and argument.id in constants:
        return constants[argument.id]
    raise AssertionError(f"event type is not a literal or a module constant: {ast.dump(argument)}")


def event_types_written() -> set[str]:
    types: set[str] = set()
    for path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = module_string_constants(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and called_name(node) == ADD_EVENT:
                types.add(event_type_of(node.args[EVENT_TYPE_POSITION], constants))
    return types


def test_the_walk_finds_the_event_types_the_code_writes() -> None:
    written = event_types_written()
    assert {"incident_opened", "action_succeeded", "approval_requested", "state_changed"} <= written


def test_every_event_type_written_has_a_sentence_for_the_activity_feed() -> None:
    written = event_types_written()
    missing = written - set(words.EVENT_SENTENCES) - {words.STATE_CHANGED_EVENT}
    assert missing == set()


def test_every_sentence_names_the_incident_it_is_about() -> None:
    for template in words.EVENT_SENTENCES.values():
        assert "{title}" in template
        assert "Disk on demo-1" in template.format(title="Disk on demo-1", actor="worker")
