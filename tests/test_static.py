import html.parser
import pathlib
import re

STATIC = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src"
    / "gnucash_quick_expense"
    / "static"
)
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
SCRIPT = (STATIC / "app.js").read_text(encoding="utf-8")
STYLE = (STATIC / "app.css").read_text(encoding="utf-8")


class _Tags(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.script_text: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        self._in_script = tag == "script"

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self.script_text.append(data)


def _tags() -> _Tags:
    parser = _Tags()
    parser.feed(INDEX)
    return parser


def test_scripts_are_external_only():
    parser = _tags()
    scripts = [attrs for tag, attrs in parser.tags if tag == "script"]
    assert scripts and all(attrs.get("src") for attrs in scripts)
    assert "".join(parser.script_text).strip() == ""


def test_page_has_no_inline_styles_handlers_or_remote_resources():
    for _, attrs in _tags().tags:
        assert "style" not in attrs
        assert not [name for name in attrs if name.startswith("on")]
    assert "http://" not in INDEX
    assert "https://" not in INDEX
    assert "http" not in STYLE
    assert "@import" not in STYLE


def test_credentials_fields_support_password_managers():
    attrs = {a.get("id"): a for _, a in _tags().tags if a.get("id")}
    assert attrs["username"].get("autocomplete") == "username"
    assert attrs["password"].get("autocomplete") == "current-password"
    assert attrs["password"].get("type") == "password"


def test_amount_fields_ask_for_a_decimal_keypad():
    attrs = {a.get("id"): a for _, a in _tags().tags if a.get("id")}
    assert attrs["amount"].get("inputmode") == "decimal"
    assert attrs["to-amount"].get("inputmode") == "decimal"


def test_to_field_is_a_combobox():
    attrs = {a.get("id"): a for _, a in _tags().tags if a.get("id")}
    assert attrs["to"].get("role") == "combobox"
    assert attrs["to-options"].get("role") == "listbox"


def test_script_normalizes_amounts_without_turning_them_into_numbers():
    assert 'normalize("NFKC")' in SCRIPT
    for forbidden in ("parseFloat", "parseInt", "Number(", "toFixed"):
        assert forbidden not in SCRIPT


def test_script_keeps_credentials_out_of_storage():
    for forbidden in ("localStorage", "sessionStorage", "document.cookie", "indexedDB"):
        assert forbidden not in SCRIPT


def test_script_inserts_no_html():
    assert not re.search(r"\.(inner|outer)HTML\s*=", SCRIPT)
    assert "insertAdjacentHTML" not in SCRIPT
    assert "eval(" not in SCRIPT
