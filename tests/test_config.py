import pathlib

import pytest

from gnucash_quick_expense import config

EXAMPLE = pathlib.Path(__file__).resolve().parents[1] / "config.example.yaml"


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("Assets:**:Cash", "Assets:Yen:Cash", True),
        ("Assets:**:Cash", "Assets:Yen:Cash:Glovebox", False),
        ("Assets:**:Glovebox", "Assets:Yen:Cash:Glovebox", True),
        (
            "Assets:**:Transit Card",
            "Assets:Yen:Prepaid:Transit Card",
            True,
        ),
        ("Assets:**:Cash", "Assets:Cash", False),
        ("Expenses:**", "Expenses:Food:Dining", True),
        ("Expenses:**", "Expenses", False),
        ("Expenses:*", "Expenses:Food:Dining", False),
        ("Expenses:*", "Expenses:Food", True),
        ("Expenses:**", "Income:Salary", False),
        ("Assets:**:cash", "Assets:Yen:Cash", False),
    ],
)
def test_matches(pattern, path, expected):
    assert config.matches(pattern, path) is expected


def test_load_reads_the_example():
    loaded = config.load(EXAMPLE)
    assert loaded.from_accounts.patterns == ("Assets:**:Cash",)
    assert loaded.from_accounts.default == "Assets:Current Assets:Cash"
    assert loaded.to_accounts.patterns == ("Expenses:**",)
    assert loaded.to_accounts.default == "Expenses:Dining"


def test_load_allows_a_missing_default(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "from_accounts: {patterns: ['Assets:**:Cash']}\n"
        "to_accounts: {patterns: ['Expenses:**']}\n"
    )
    assert config.load(path).to_accounts.default is None


@pytest.mark.parametrize(
    "text",
    [
        "from_accounts: {patterns: []}\nto_accounts: {patterns: ['Expenses:**']}\n",
        "to_accounts: {patterns: ['Expenses:**']}\n",
        "from_accounts: {patterns: ['A:**']}\nto_accounts: {patterns: 'Expenses:**'}\n",
        "from_accounts: {patterns: ['A:**']}\nto_accounts: {patterns: [1]}\n",
        (
            "from_accounts: {patterns: ['A:**'], default: 3}\n"
            "to_accounts: {patterns: ['E:**']}\n"
        ),
        "- not a mapping\n",
        "from_accounts: [\n",
    ],
    ids=[
        "empty-patterns",
        "missing-section",
        "patterns-not-a-list",
        "pattern-not-a-string",
        "default-not-a-string",
        "not-a-mapping",
        "invalid-yaml",
    ],
)
def test_load_rejects_invalid_files(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(config.ConfigError):
        config.load(path)
