"""Guard the staged multi-agent architecture without touching business payloads."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / ".omp" / "agents"


def test_engineering_agents_exist():
    for name in ("data-governance-specialist.md", "decision-quality-reviewer.md"):
        path = AGENTS / name
        assert path.exists(), name
        text = path.read_text(encoding="utf-8")
        assert "EvidenceRef" in text
        assert "只读" in text
        assert "actor_can_execute" in text


def test_business_roles_are_not_registered_as_agents():
    readme = (AGENTS / "README.md").read_text(encoding="utf-8")
    for role in ("厂长", "线长", "质量", "设备", "工艺", "供应链"):
        assert role in readme
    assert "不是工程代理" in readme


def test_orchestrator_has_governance_and_review_gates():
    text = (AGENTS / "orchestrator.md").read_text(encoding="utf-8")
    assert "data-governance-specialist" in text
    assert "decision-quality-reviewer" in text
    assert "不得伪造完成状态" in text


if __name__ == "__main__":
    test_engineering_agents_exist()
    test_business_roles_are_not_registered_as_agents()
    test_orchestrator_has_governance_and_review_gates()
    print("test_agent_architecture: 3/3 PASS")
