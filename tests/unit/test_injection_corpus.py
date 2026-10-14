from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel

from noc.config import PACKAGE_DIR
from noc.policy.engine import PolicyInputs, evaluate_action
from noc.policy.loader import load_policy
from noc.policy.models import (
    ActionCandidate,
    AutomationLevel,
    Environment,
    Gate,
    ResourceFacts,
    SituationFacts,
    TargetFacts,
)
from noc.tools.sanitize import render_tool_result, scan_injection
from noc_shared.permissions import PermissionClass

CORPUS_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "payloads" / "corpus.yaml"
POLICY = load_policy(PACKAGE_DIR / "policy" / "default_policy.yaml")
RESTART = "restart_service"
MAX_CHARS = 20000


class Family(BaseModel):
    name: str
    expect_flag: bool
    payload: str


class Corpus(BaseModel):
    families: list[Family]


def load_corpus() -> list[Family]:
    return Corpus.model_validate(yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8"))).families


FAMILIES = load_corpus()
IDS = [family.name for family in FAMILIES]


def rendered(payload: str) -> tuple[str, list[str]]:
    result = render_tool_result(
        tool="get_service_logs",
        ref="T1",
        ok=True,
        data={"service": "demo-shop.service", "lines": ["before", payload, "after"]},
        error=None,
        untrusted_fields=("lines",),
        max_chars=MAX_CHARS,
    )
    return result.text, result.injection_flags


def policy_decision(
    resource: ResourceFacts, flagged: bool, level: AutomationLevel = AutomationLevel.AUTO_SAFE
):
    inputs = PolicyInputs(
        candidate=ActionCandidate(action_type=RESTART, resource_id="svc:x", evidence_refs=("T1",)),
        definition=POLICY.actions.get(RESTART),
        target=TargetFacts(
            environment=Environment.LAB, automation_level=level, auto_actions=(RESTART,)
        ),
        resource=resource,
        situation=SituationFacts.model_validate(
            {
                "execution_enabled": True,
                "diagnosis_confidence": 0.95,
                "suspected_injection": flagged,
            }
        ),
    )
    return evaluate_action(inputs, POLICY.weights, POLICY.version)


def test_the_corpus_has_the_ten_families_of_the_security_scenario() -> None:
    assert len(FAMILIES) == 10
    assert len(set(IDS)) == 10


@pytest.mark.parametrize("family", FAMILIES, ids=IDS)
def test_payload_cannot_close_or_forge_a_prompt_tag(family: Family) -> None:
    text, _ = rendered(family.payload)
    assert text.count("<untrusted_data") == 1
    assert text.count("</untrusted_data>") == 1
    assert text.count("<tool_result") == 1
    assert text.count("</tool_result>") == 1
    assert "<incident_brief" not in text
    assert "<focus_questions" not in text


@pytest.mark.parametrize("family", FAMILIES, ids=IDS)
def test_payload_stays_inside_the_untrusted_block(family: Family) -> None:
    text, _ = rendered(family.payload)
    start = text.index("<untrusted_data")
    end = text.index("</untrusted_data>")
    outside = text[:start] + text[end:]
    first_words = family.payload.split()[0:3]
    assert " ".join(first_words) not in outside


@pytest.mark.parametrize("family", FAMILIES, ids=IDS)
def test_scanner_flags_the_families_it_is_expected_to_flag(family: Family) -> None:
    _, flags = rendered(family.payload)
    assert bool(flags) is family.expect_flag
    assert bool(scan_injection(family.payload)) is family.expect_flag


def test_scanner_gaps_are_known_and_listed() -> None:
    missed = sorted(family.name for family in FAMILIES if not family.expect_flag)
    assert missed == ["markdown_link", "multilingual", "unicode_homoglyph"]


@pytest.mark.parametrize("family", FAMILIES, ids=IDS)
def test_following_the_payload_never_passes_the_policy_gates(family: Family) -> None:
    unregistered = policy_decision(ResourceFacts(registered=False), flagged=family.expect_flag)
    protected = policy_decision(
        ResourceFacts(registered=True, allowed_actions=(RESTART,), protected=True),
        flagged=family.expect_flag,
    )
    for decision in (unregistered, protected):
        assert decision.permission_class is PermissionClass.BLOCKED
        assert not decision.auto_executable
    assert Gate.UNREGISTERED_RESOURCE in unregistered.gate_failures
    assert Gate.PROTECTED_RESOURCE in protected.gate_failures


@pytest.mark.parametrize("family", [f for f in FAMILIES if f.expect_flag], ids=lambda f: f.name)
def test_a_flagged_injection_always_forces_a_human_approval(family: Family) -> None:
    registered = ResourceFacts(registered=True, allowed_actions=(RESTART,))
    clean = policy_decision(registered, flagged=False)
    flagged = policy_decision(registered, flagged=True)
    assert clean.auto_executable
    assert not flagged.auto_executable
    assert flagged.permission_class is not PermissionClass.SAFE_ACTION
