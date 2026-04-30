from pathlib import Path


def _read_kong_config() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return (repo_root / "kong" / "kong.yml").read_text(encoding="utf8")


def _route_section(config_text: str, route_name: str) -> str:
    marker = f"- name: {route_name}"
    assert marker in config_text, f"Route {route_name} not found in kong/kong.yml"
    trailing = config_text.split(marker, 1)[1]
    return trailing.split("\n  - name: ", 1)[0]


def test_kong_has_tiered_route_variants():
    config_text = _read_kong_config()

    expected_routes = [
        "ai-inference-routes-pro",
        "ai-inference-routes-basic",
        "ai-inference-routes-free",
        "ai-inference-routes-default",
        "execution-routes-pro",
        "execution-routes-basic",
        "execution-routes-free",
        "execution-routes-default",
        "api-routes-pro",
        "api-routes-basic",
        "api-routes-free",
        "api-routes-default",
    ]

    for route_name in expected_routes:
        assert f"- name: {route_name}" in config_text



def test_kong_api_tier_limits_match_quota_defaults():
    config_text = _read_kong_config()

    expected_limits = {
        "pro": ("minute: 1200", "hour: 24000"),
        "basic": ("minute: 300", "hour: 6000"),
        "free": ("minute: 60", "hour: 1200"),
        "default": ("minute: 60", "hour: 1200"),
    }

    for tier_name, (minute_limit, hour_limit) in expected_limits.items():
        section = _route_section(config_text, f"api-routes-{tier_name}")
        assert minute_limit in section
        assert hour_limit in section



def test_kong_tier_header_matchers_present_for_tiered_routes():
    config_text = _read_kong_config()

    for tier_name in ("pro", "basic", "free"):
        for route_prefix in ("ai-inference-routes", "execution-routes", "api-routes"):
            section = _route_section(config_text, f"{route_prefix}-{tier_name}")
            assert "x-autosaham-tier:" in section
            assert f"- {tier_name}" in section
