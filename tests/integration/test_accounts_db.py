from gnucash_quick_expense import accounts


def test_fetch_all_builds_paths_under_the_root_account(gnucash_db):
    by_path = {a.path: a for a in accounts.fetch_all(gnucash_db)}
    assert "Assets:Dollar:Cash" in by_path
    assert "Expenses:Food:Dining" in by_path
    assert not [p for p in by_path if p.startswith(("Root Account", "Template Root"))]
    usd = by_path["Assets:Dollar:Cash"]
    assert (usd.mnemonic, usd.fraction, usd.usable) == ("USD", 100, True)
    assert by_path["Assets:Yen"].usable is False
    assert by_path["Expenses:Old"].usable is False


def test_fetch_all_skips_the_template_tree(gnucash_db):
    paths = [a.path for a in accounts.fetch_all(gnucash_db)]
    # The template root has its own "Assets" child, which must not appear twice.
    assert paths.count("Assets") == 1
