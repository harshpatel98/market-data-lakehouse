import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "ci.yml")


def test_ci_workflow_exists():
    assert os.path.exists(WORKFLOW), "create .github/workflows/ci.yml"


def test_ci_workflow_runs_tests_on_push_and_pr():
    text = open(WORKFLOW).read()
    assert "pytest" in text
    assert "actions/checkout" in text
    assert "push" in text and "pull_request" in text
