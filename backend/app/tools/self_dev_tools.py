"""Self-development tools — propose_change, run_self_test, deploy_change."""

import json

from app.self_dev import get_shadow_sandbox


def propose_change(file_path: str, content: str) -> str:
    shadow = get_shadow_sandbox()
    if shadow.status == "IDLE":
        shadow.create_shadow()
    return shadow.apply_change(file_path, content)


def run_self_test() -> str:
    shadow = get_shadow_sandbox()
    if shadow.status == "IDLE":
        return "No shadow initialized. Use propose_change first."
    results = shadow.run_tests()
    return json.dumps(results, indent=2) if isinstance(results, dict) else str(results)


def deploy_change() -> str:
    shadow = get_shadow_sandbox()
    if shadow.status == "IDLE":
        return "No shadow initialized."
    return shadow.deploy_to_live()
