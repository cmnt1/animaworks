from pathlib import Path

BATTLE_CSS = Path(__file__).resolve().parents[3] / "server/static/battle/style.css"
PAGE_ONLY_BEGIN = "/* STANDALONE_PAGE_ONLY_BEGIN */"
PAGE_ONLY_END = "/* STANDALONE_PAGE_ONLY_END */"


def test_battle_css_selectors_are_scoped_to_the_battle_root():
    in_page_only_block = False
    selectors = []

    for line_number, line in enumerate(BATTLE_CSS.read_text(encoding="utf-8").splitlines(), start=1):
        if PAGE_ONLY_BEGIN in line:
            assert not in_page_only_block, "nested standalone-only CSS block"
            in_page_only_block = True
            continue
        if PAGE_ONLY_END in line:
            assert in_page_only_block, "standalone-only CSS block ended without starting"
            in_page_only_block = False
            continue
        if in_page_only_block or "{" not in line or line.lstrip().startswith("@"):
            continue

        prelude = line.split("{", maxsplit=1)[0].strip()
        if not prelude:
            continue
        for selector in prelude.split(","):
            selectors.append((line_number, selector.strip()))

    assert not in_page_only_block, "standalone-only CSS block was not closed"
    assert selectors, "no CSS selectors were checked"
    unscoped = [(line_number, selector) for line_number, selector in selectors if not selector.startswith(".aw-battle")]
    assert not unscoped, "unscoped battle selectors: " + "; ".join(
        f"line {line_number}: {selector}" for line_number, selector in unscoped
    )
