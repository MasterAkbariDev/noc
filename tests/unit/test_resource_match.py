from types import SimpleNamespace

from noc.orchestration.resource_match import process_names, registered_process_match

CPU_EXCERPT = '"cmdline": "python report-gen --burn", "cpu_percent": 99.1, "name": "report-gen"'
MEMORY_EXCERPT = '"name": "demo-shop", "rss_mb": 300'


def finding(*excerpts: str) -> SimpleNamespace:
    return SimpleNamespace(evidence=[{"excerpt": text} for text in excerpts])


def test_process_names_come_only_from_cpu_evidence() -> None:
    findings = [finding(CPU_EXCERPT, MEMORY_EXCERPT), finding(CPU_EXCERPT)]
    assert process_names(findings) == ["report-gen"]  # type: ignore[arg-type]


def test_a_burning_process_maps_to_its_registered_job() -> None:
    resources = [
        ("svc:demo-shop", "demo-shop.service"),
        ("job:report-gen", "noc-chaos-cpu-burn.service"),
    ]
    assert registered_process_match(["report-gen"], resources) == "job:report-gen"


def test_an_unregistered_process_maps_to_nothing() -> None:
    resources = [("svc:demo-shop", "demo-shop.service")]
    assert registered_process_match(["noc"], resources) is None
    assert registered_process_match([], resources) is None
