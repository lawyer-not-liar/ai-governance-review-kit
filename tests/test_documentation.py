import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1]


def test_readme_leads_with_conversational_skill() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert readme.index("## Install the conversational skill") < readme.index(
        "## Use the Python engine directly"
    )
    assert "docs/CONVERSATIONAL_SKILL.md" in readme
    assert "illustrative" in readme.lower()


def test_citation_metadata_uses_repository_identity_and_current_release() -> None:
    citation = (PROJECT_ROOT / "CITATION.cff").read_text(encoding="utf-8")

    assert "name: lawyer-not-liar" in citation
    assert "version: 0.1.2" in citation
    assert 'date-released: "2026-08-12"' in citation
    assert "https://github.com/lawyer-not-liar/ai-governance-review-kit" in citation
    assert "given-names:" not in citation
    assert "family-names:" not in citation


def test_readme_presents_one_skill_for_codex_and_claude_before_python() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    codex = readme.index("### Install in Codex")
    claude = readme.index("### Install in Claude or Claude Desktop")
    python = readme.index("## Use the Python engine directly")

    assert "one self-contained ZIP" in readme
    assert codex < python
    assert claude < python
    assert "$ai-governance-review" in readme
    assert "Customize > Skills" in readme
    assert "Review this proposed AI use." in readme


def test_readme_covers_each_supported_conversational_workflow() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    workflows = {
        "Review a short description",
        "Review a document or existing intake",
        "Resolve missing or conflicting facts",
        "Clarify supporting evidence",
        "Reassess after facts change",
        "Understand the draft",
        "Discuss a human decision",
        "Export a review",
        "Continue when the engine cannot run",
    }
    headings = set(re.findall(r"^### (?:\d+\. )?(.+)$", readme, flags=re.MULTILINE))

    assert workflows <= headings
    assert readme.count("**Try:**") >= len(workflows)
    assert readme.count("**Boundary:**") >= len(workflows)


def test_readme_installation_has_verification_troubleshooting_and_official_sources() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "## Verify the installation" in readme
    assert "## Troubleshooting" in readme
    assert "https://learn.chatgpt.com/docs/build-skills" in readme
    assert "https://support.claude.com/en/articles/12512180-use-skills-in-claude" in readme
    assert "Python 3.11" in readme
    assert "**+ Create skill**" in readme
    assert "**Upload a skill**" in readme
    assert "Add > Upload a skill" not in readme
    assert "Ask Codex to install it" in readme


def test_readme_keeps_host_and_export_confidentiality_boundaries_clear() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "Local-first describes the engine" in readme
    assert "host's data practices" in readme
    assert '"$HOME/ai-governance-review-output/sanitized-bundle"' in readme
    assert "public GitHub issue" not in readme


def test_first_run_prompt_supplies_material_routing_facts() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    verification = readme.split("## Verify the installation", 1)[1].split(
        "## Your first review", 1
    )[0]

    assert all(
        fact in verification
        for fact in (
            "personal or sensitive data",
            "training or fine-tuning",
            "cross-border transfers",
            "external distribution",
            "decisions about people",
        )
    )


def test_alpha_workbook_is_not_presented_as_attorney_interface() -> None:
    alpha = (PROJECT_ROOT / "docs/ALPHA_VALIDATION.md").read_text(encoding="utf-8")

    assert "maintainer evaluation artifact" in alpha.lower()


def test_maintainer_runtime_guide_reuses_supported_python_launcher() -> None:
    raw_guide = (PROJECT_ROOT / "docs/CONVERSATIONAL_SKILL.md").read_text(encoding="utf-8")
    guide = " ".join(raw_guide.lower().split())

    assert "python 3.11 or newer" in guide
    assert all(launcher in guide for launcher in ("`python3`", "`python`", "`py -3.11`"))
    assert "same selected launcher" in guide
    assert "<python-launcher> scripts/review_ai_use.py self-check" in guide
    assert "self-contained" in guide
    assert "does not install python packages" in guide
    assert "setup_runtime.py" not in guide
    assert ".runtime-deps" not in guide
    assert "deterministic policy validation was not run" in guide
    assert "do not claim equivalent assurance" in guide


def test_readme_describes_dependency_free_skill_runtime() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8").lower()

    assert "does not download or install python packages" in readme
    assert "standard-library fallback" in readme
    assert "setup_runtime.py" not in readme
    assert ".runtime-deps" not in readme


def test_attorney_guides_explain_the_accurate_default_result() -> None:
    documents = (
        " ".join((PROJECT_ROOT / "README.md").read_text(encoding="utf-8").lower().split()),
        " ".join(
            (PROJECT_ROOT / "docs/CONVERSATIONAL_SKILL.md")
            .read_text(encoding="utf-8")
            .lower()
            .split()
        ),
    )

    expected = (
        "engine-rendered presentation text",
        "engine-supplied presentation facts",
        "focuses on active findings",
        "inactive checks only when you ask",
        "does not mention inactive checks",
    )
    assert all(requirement in document for document in documents for requirement in expected)


def test_readme_verification_prompt_supplies_required_review_facts() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8").lower()
    prompt = readme.split("use the ai governance review skill.", 1)[1].split("```", 1)[0]

    assert "assistive" in prompt
    assert "affected people" in prompt


def test_detailed_guide_uses_one_portable_zip_for_both_hosts() -> None:
    guide = (PROJECT_ROOT / "docs/CONVERSATIONAL_SKILL.md").read_text(encoding="utf-8")

    assert "same self-contained ZIP" in guide
    assert "~/.agents/skills" in guide
    assert "Customize > Skills" in guide
    assert "**+ Create skill**" in guide
    assert "**Upload a skill**" in guide
    assert "$ai-governance-review" in guide


def test_example_models_one_highest_impact_question_per_turn() -> None:
    guide = (PROJECT_ROOT / "docs/CONVERSATIONAL_SKILL.md").read_text(encoding="utf-8")
    example = guide.split("```text", 1)[1].split("```", 1)[0]
    skill_turns = [turn for turn in example.split("\n\n") if turn.startswith("Skill:")]
    question_turns = [turn for turn in skill_turns if "?" in turn]

    assert len(question_turns) >= 3
    assert all(turn.count("?") == 1 and " and " not in turn.lower() for turn in question_turns)


def test_readme_local_paths_resolve():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    references = {
        match.rstrip("/.,")
        for match in re.findall(r"(?:examples|policies)/[A-Za-z0-9_./-]+", readme)
        if "<" not in match
    }

    missing = sorted(path for path in references if not (PROJECT_ROOT / path).exists())

    assert missing == []


def test_readme_markdown_links_resolve():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    local_links = [
        target
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", readme)
        if "://" not in target and not target.startswith("#")
    ]

    missing = sorted(link for link in local_links if not (PROJECT_ROOT / link).exists())

    assert missing == []
