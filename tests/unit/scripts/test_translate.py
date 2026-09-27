from __future__ import annotations

import re
from pathlib import Path

from scripts.i18n.engine import TranslationResponse
from scripts.i18n.pipeline import Target, Translator
from scripts.i18n.protect import protect_text
from scripts.i18n.segment import split_markdown


class EchoEngine:
    def __init__(self, transform=None) -> None:
        self.calls: list[str] = []
        self.transform = transform or (lambda text: text)

    def translate(self, _system: str, user: str) -> TranslationResponse:
        self.calls.append(user)
        return TranslationResponse(self.transform(user), input_tokens=17, output_tokens=11, model="fake-model")


def _translator(
    root: Path,
    target: Target,
    engine: EchoEngine,
    *,
    fallback: EchoEngine | None = None,
    manifest_name: str = "manifest.json",
) -> Translator:
    configuration = {
        "defaults": {
            "engine": "fake",
            "fallback_engine": "fallback" if fallback else "",
            "batch_chars": 6000,
            "concurrency": 3,
        },
        "engines": {
            "fake": {"kind": "openai", "model": "fake-model"},
            "fallback": {"kind": "openai", "model": "fallback-model"},
        },
    }
    engines = {"fake": engine}
    if fallback:
        engines["fallback"] = fallback
    return Translator(
        root=root,
        configuration=configuration,
        targets=[target],
        glossary=[],
        engines=engines,
        manifest_path=root / manifest_name,
    )


def _docs_target(*, links: tuple[tuple[str, str], ...] = ()) -> Target:
    return Target(
        name="docs",
        src="docs/ja",
        dst="docs/{lang}",
        include=("**/*.md",),
        copy=(),
        header="html_comment",
        link_rewrite=links,
    )


def test_protection_round_trip_preserves_code_placeholders_urls_and_frontmatter() -> None:
    source = (
        "---\n"
        "name: sample-skill\n"
        "description: >-\n"
        "  Use when: {anima_name} でpermissions.mdの処理をする。リンク [docs](https://example.test/a)。\n"
        "tags: [stable, cli]\n"
        "---\n\n"
        "値は {{literal}} と `{task.id}`。\n\n"
        "```python\nvalue = '{task_id}'\n```\n"
    )
    frontmatter, body = split_markdown(source)
    protected_frontmatter = protect_text(frontmatter.text, frontmatter=True)
    protected_body = protect_text(body.text)

    assert protected_frontmatter.text != frontmatter.text
    assert "Use when:" not in protected_frontmatter.text
    assert protected_frontmatter.restore(protected_frontmatter.text) == frontmatter.text
    assert protected_body.restore(protected_body.text) == body.text
    assert "name: sample-skill" in protected_frontmatter.restore(protected_frontmatter.text)
    assert "https://example.test/a" in protected_frontmatter.restore(protected_frontmatter.text)
    assert any(value == "permissions.md" for value in protected_frontmatter.values.values())
    assert "```python\nvalue = '{task_id}'\n```\n" in protected_body.values.values()


def test_splitter_ignores_hash_lines_inside_fenced_code() -> None:
    from scripts.i18n.segment import split_markdown

    segments = split_markdown("# First\n\n```text\n# not a heading\n```\n\n## Second\nbody\n")

    assert len(segments) == 2
    assert "# not a heading" in segments[0].text
    assert segments[1].text.startswith("## Second")


def test_only_changed_section_is_translated_and_insertions_reuse_other_sections(tmp_path: Path) -> None:
    source_dir = tmp_path / "docs" / "ja"
    source_dir.mkdir(parents=True)
    source = source_dir / "guide.md"
    source.write_text("# Alpha\nAlpha source.\n\n## Beta\nBeta source.\n\n## Gamma\nGamma source.\n", encoding="utf-8")
    engine = EchoEngine()
    translator = _translator(tmp_path, _docs_target(), engine)

    assert translator.run("docs", requested_langs=["en"]) == 0
    first_call_count = len(engine.calls)
    source.write_text(
        "# Alpha\nAlpha source.\n\n## Beta\nBeta revised.\n\n## Gamma\nGamma source.\n",
        encoding="utf-8",
    )
    assert translator.run("docs", requested_langs=["en"]) == 0
    assert len(engine.calls) - first_call_count == 1
    assert "Beta revised." in engine.calls[-1]
    assert "Alpha source." not in engine.calls[-1]
    assert "Gamma source." not in engine.calls[-1]

    calls_before_insert = len(engine.calls)
    source.write_text(
        "# Alpha\nAlpha source.\n\n## Beta\nBeta revised.\n\n## Gamma\nGamma source.\n\n## Delta\nDelta source.\n",
        encoding="utf-8",
    )
    assert translator.run("docs", requested_langs=["en"]) == 0
    assert len(engine.calls) - calls_before_insert == 1
    assert engine.calls[-1].strip() == "## Delta\nDelta source."


def test_malformed_batch_retries_each_section_only_once(tmp_path: Path) -> None:
    source_dir = tmp_path / "docs" / "ja"
    source_dir.mkdir(parents=True)
    (source_dir / "guide.md").write_text(
        "# 第一節\nこれは説明です。\n\n## 第二節\nこれは補足です。\n", encoding="utf-8"
    )
    engine = EchoEngine(lambda _text: "malformed response")
    translator = _translator(tmp_path, _docs_target(), engine)

    assert translator.run("docs", requested_langs=["en"]) == 2
    # One malformed batch request, then exactly one single-section retry per section.
    assert len(engine.calls) == 3
    assert translator.manifest["files"]["docs/en/guide.md"]["statuses"] == ["failed", "failed"]


def test_invalid_single_section_is_retried_once_before_failure(tmp_path: Path) -> None:
    source_dir = tmp_path / "docs" / "ja"
    source_dir.mkdir(parents=True)
    (source_dir / "guide.md").write_text("# 日本語\nこれは文章です。\n", encoding="utf-8")
    engine = EchoEngine()
    translator = _translator(tmp_path, _docs_target(), engine)

    assert translator.run("docs", requested_langs=["en"]) == 2
    assert len(engine.calls) == 2
    assert translator.manifest["files"]["docs/en/guide.md"]["statuses"] == ["failed"]


def test_failed_changed_section_keeps_its_previous_translation(tmp_path: Path) -> None:
    source_dir = tmp_path / "docs" / "ja"
    source_dir.mkdir(parents=True)
    source = source_dir / "guide.md"
    source.write_text("# 見出し\n以前の文章です。\n", encoding="utf-8")
    engine = EchoEngine(lambda text: text.replace("見出し", "Heading").replace("以前の文章です。", "Previous text."))
    translator = _translator(tmp_path, _docs_target(), engine)

    assert translator.run("docs", requested_langs=["en"]) == 0
    source.write_text("# 見出し\n新しい文章です。\n", encoding="utf-8")
    engine.transform = lambda text: text

    assert translator.run("docs", requested_langs=["en"]) == 2
    output = (tmp_path / "docs" / "en" / "guide.md").read_text(encoding="utf-8")
    assert "Previous text." in output
    assert "新しい文章です。" not in output
    assert translator.manifest["files"]["docs/en/guide.md"]["statuses"] == ["failed"]


def test_lost_sentinel_fails_validation_and_uses_fallback(tmp_path: Path) -> None:
    source_dir = tmp_path / "docs" / "ja"
    source_dir.mkdir(parents=True)
    (source_dir / "guide.md").write_text(
        "# セクション\nこれは説明です。\n\n```text\ncode stays byte-identical\n```\n",
        encoding="utf-8",
    )
    primary = EchoEngine(lambda text: re.sub(r"⟦P\d+⟧", "", text, count=1))
    fallback = EchoEngine(
        lambda text: text.replace("セクション", "Section").replace("これは説明です。", "This is an explanation.")
    )
    translator = _translator(tmp_path, _docs_target(), primary, fallback=fallback)

    assert translator.run("docs", requested_langs=["en"]) == 0
    assert primary.calls
    assert fallback.calls
    output = (tmp_path / "docs" / "en" / "guide.md").read_text(encoding="utf-8")
    assert "# Section" in output
    assert "This is an explanation." in output
    assert "```text\ncode stays byte-identical\n```" in output
    record = translator.manifest["files"]["docs/en/guide.md"]
    assert record["statuses"] == ["translated"]


def test_check_detects_source_changes(tmp_path: Path) -> None:
    source_dir = tmp_path / "docs" / "ja"
    source_dir.mkdir(parents=True)
    source = source_dir / "guide.md"
    source.write_text("# Guide\nSource text.\n", encoding="utf-8")
    translator = _translator(tmp_path, _docs_target(), EchoEngine())

    assert translator.run("docs", requested_langs=["en"]) == 0
    assert translator.run("docs", requested_langs=["en"], check=True) == 0
    source.write_text("# Guide\nChanged source text.\n", encoding="utf-8")
    assert translator.run("docs", requested_langs=["en"], check=True) == 1


def test_check_detects_generated_files_without_a_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "docs" / "ja"
    source_dir.mkdir(parents=True)
    (source_dir / "guide.md").write_text("# Guide\nSource text.\n", encoding="utf-8")
    translator = _translator(tmp_path, _docs_target(), EchoEngine())

    assert translator.run("docs", requested_langs=["en"]) == 0
    stale = tmp_path / "docs" / "en" / "retired.md"
    stale.write_text("# Retired\n", encoding="utf-8")

    assert translator.run("docs", requested_langs=["en"], check=True) == 1


def test_templates_have_no_headers_and_json_py_are_byte_copied(tmp_path: Path) -> None:
    source_dir = tmp_path / "templates" / "ja"
    source_dir.mkdir(parents=True)
    (source_dir / "guide.md").write_text("# Guide\nTemplate body.\n", encoding="utf-8")
    json_bytes = b'{"permissions": ["read"]}\n'
    python_bytes = b"VALUE = 7\n"
    (source_dir / "permissions.json").write_bytes(json_bytes)
    (source_dir / "helper.py").write_bytes(python_bytes)
    target = Target(
        name="templates",
        src="templates/ja",
        dst="templates/{lang}",
        include=("**/*.md",),
        copy=("**/*.json", "**/*.py"),
        header="none",
    )
    translator = _translator(tmp_path, target, EchoEngine())

    assert translator.run("templates", requested_langs=["en"]) == 0
    output_dir = tmp_path / "templates" / "en"
    assert (output_dir / "guide.md").read_text(encoding="utf-8") == "# Guide\nTemplate body.\n"
    assert not (output_dir / "guide.md").read_text(encoding="utf-8").startswith("<!-- 自動翻訳")
    assert (output_dir / "permissions.json").read_bytes() == json_bytes
    assert (output_dir / "helper.py").read_bytes() == python_bytes
    assert translator.manifest["files"]["templates/en/guide.md"]["source_sha256"]
    assert translator.run("templates", requested_langs=["en"], check=True) == 0


def test_readme_rewrites_only_link_destinations_for_each_language(tmp_path: Path) -> None:
    source = tmp_path / "README_ja.md"
    source.write_text(
        "# README\nSee [guide](docs/ja/reference/api.md) and [other](README_ja.md).\n"
        "\n```md\n[example](docs/ja/not-a-link.md)\n```\n",
        encoding="utf-8",
    )
    target = Target(
        name="readme",
        src="README_ja.md",
        dst={"en": "README.md", "ko": "README_ko.md"},
        include=("README_ja.md",),
        copy=(),
        header="html_comment",
        link_rewrite=(("docs/ja/", "docs/{lang}/"), ("README_ja.md", "{readme}")),
    )
    translator = _translator(tmp_path, target, EchoEngine())

    assert translator.run("readme", requested_langs=["en", "ko"]) == 0
    english = (tmp_path / "README.md").read_text(encoding="utf-8")
    korean = (tmp_path / "README_ko.md").read_text(encoding="utf-8")
    for output, readme in ((english, "README.md"), (korean, "README_ko.md")):
        assert "](docs/" + ("en" if readme == "README.md" else "ko") + "/reference/api.md)" in output
        assert f"]({readme})" in output
        assert "[example](docs/ja/not-a-link.md)" in output
        assert "source-sha256=" in output.splitlines()[1]
