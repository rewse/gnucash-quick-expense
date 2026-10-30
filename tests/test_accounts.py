from gnucash_quick_expense import accounts
from gnucash_quick_expense import config


def _account(path: str, usable: bool = True, mnemonic: str = "JPY") -> accounts.Account:
    return accounts.Account(
        guid=path.replace(":", "_")[:32],
        path=path,
        commodity_guid=f"c-{mnemonic}",
        mnemonic=mnemonic,
        fraction=1 if mnemonic == "JPY" else 100,
        usable=usable,
    )


ALL = [
    _account("Expenses:Food:Dining"),
    _account("Assets:Dollar:Cash", mnemonic="USD"),
    _account("Assets:Yen", usable=False),
    _account("Assets:Yen:Cash"),
    _account("Expenses:Old", usable=False),
    _account("Expenses", usable=False),
]


def test_choose_returns_usable_matches_in_path_order():
    choice = config.AccountChoice(("Assets:**:Cash",), None)
    assert [a.path for a in accounts.choose(ALL, choice)] == [
        "Assets:Yen:Cash",
        "Assets:Dollar:Cash",
    ]


def test_choose_skips_placeholder_and_hidden_accounts():
    choice = config.AccountChoice(("Expenses:**", "Assets:*"), None)
    paths = [a.path for a in accounts.choose(ALL, choice)]
    assert paths == ["Expenses:Food:Dining"]


def test_choose_lists_an_account_once_when_several_patterns_match():
    choice = config.AccountChoice(("Expenses:**", "Expenses:*:Dining"), None)
    assert [a.path for a in accounts.choose(ALL, choice)] == ["Expenses:Food:Dining"]


def test_default_path_is_the_configured_default_when_offered():
    choice = config.AccountChoice(("Expenses:**",), "Expenses:Food:Dining")
    choices = accounts.choose(ALL, choice)
    assert accounts.default_path(choices, choice) == "Expenses:Food:Dining"


def test_default_path_is_none_when_the_default_is_not_offered():
    choice = config.AccountChoice(("Expenses:**",), "Expenses:Old")
    choices = accounts.choose(ALL, choice)
    assert accounts.default_path(choices, choice) is None
    no_default = config.AccountChoice(("Expenses:**",), None)
    assert accounts.default_path(choices, no_default) is None
