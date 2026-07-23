import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_PATH = (
    PROJECT_ROOT
    / "infra"
    / "observability"
    / "grafana"
    / "dashboards"
    / "assistant-observability.json"
)


def test_dashboard_exposes_the_bounded_tool_metrics_needed_for_operations() -> None:
    dashboard = json.loads(DASHBOARD_PATH.read_text(encoding="utf-8"))
    panels = dashboard["panels"]
    titles = {panel["title"]: panel for panel in panels}

    assert "Tool" in titles
    assert len({panel["id"] for panel in panels}) == len(panels)
    assert "agent_tool_calls_total" in titles["Tool call rate by outcome"]["targets"][0]["expr"]
    assert (
        "agent_tool_duration_seconds_bucket"
        in titles["Tool call duration p95"]["targets"][0]["expr"]
    )
    assert (
        "tool_calls_limit_exceeded_total"
        in titles["Tool call limit exceeded rate"]["targets"][0]["expr"]
    )
