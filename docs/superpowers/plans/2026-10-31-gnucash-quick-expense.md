# gnucash-quick-expense 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** スマートフォンから GnuCash の PostgreSQL に支出を 1 件ずつ INSERT する Web フォームを作り、web の `https://expense.example.com/` で公開する。

**Architecture:** Starlette のアプリが、ブラウザから送られた PostgreSQL の資格情報でリクエストごとに DB に接続し、アカウント一覧の取得、為替換算、INSERT を行う。フロントエンドは素の HTML、CSS、JavaScript の 1 ページ。web では ansible-playbooks の新しいロールが GitHub から checkout して systemd で動かし、Apache の vhost と fail2ban を付けて CloudFront の後ろに置く。

**Tech Stack:** Python 3.14（`.python-version`）、uv、Starlette、uvicorn、psycopg 3、httpx、PyYAML、pytest。Ansible、Apache、fail2ban、CloudFormation。

**Spec:** `docs/superpowers/specs/2026-10-31-gnucash-quick-expense-design.md`

## Global Constraints

- 金額は float を使わず、`decimal.Decimal` と、GnuCash と同じ分子・分母の整数で扱う。JavaScript でも金額を数値に変換しない。
- PostgreSQL の資格情報は POST の JSON 本文でだけ受け取る。ディスク、ログ、Cookie、localStorage、sessionStorage、エラーメッセージに出さない。
- DB の認証失敗（SQLSTATE `28P01`、`28000`）は HTTP 401、入力の誤りは 400、そのほかは 500。
- `reconcile_state` は `n`、`post_date` は選んだ日付の `10:59:00` UTC、`num`、`memo`、`action` は `''`、`reconcile_date`、`lot_guid` は `NULL`。
- UI は英語だけ。README は英語で、支出 1 件の追加しかできず、GnuCash のすべての機能を提供するものではないことを最初に書く。
- 公開リポジトリに個人のアカウント名、ホスト名、DB の接続先を書かない。web の値は Ansible が `config.yaml` と環境変数で渡す。
- 依存パッケージは 96 時間以上前に公開された版だけを使う（`[tool.uv] exclude-newer = "4 days"`）。`uv lock` は `XDG_CONFIG_HOME=$(mktemp -d /tmp/uvcfg.XXXXXX) uv lock` で実行する。
- Google Python Style Guide に従い、クラスや関数ではなくモジュールを import する（`from gnucash_quick_expense import money`）。
- コミットメッセージは Conventional Commits で、本文に何をなぜ変えたかを書く。スコープはモジュール名（`accounts`、`app`、`config`、`db`、`ledger`、`money`、`rates`、`web`）。
- コミットの前に `uvx --with pre-commit-uv==4.3.0 pre-commit@4.6.2 run --all-files` と `uv run --extra test pytest` を通す。新しいファイルは先に `git add` する。

## Review Focus

- iOS の日本語キーボードで入る全角の数字やピリオド（`１，２００．５`）: ブラウザが NFKC で半角に直し、カンマを落としてから送る。サーバーは ASCII 以外を 400 で拒否する。Task 1 と Task 7 にテストがある。
- 指数表記、符号付き、0、桁の欠けた小数（`1e3`、`-5`、`+5`、`0`、`.5`、`5.`）: 400 で拒否する。Task 1 にテストがある。
- 公表相場のサイトが落ちている、遅い、HTML の形が変わった: レート API は 500 にせず、GnuCash の `prices` 表のレートで計算した値を返す。欄が空になるのは、`prices` 表にもその通貨のレートが無いとき（2026-10-31 時点では EUR）だけ。Task 4 と Task 6 にテストがある。
- `To` に候補と少しだけ違う文字列（大文字小文字の違い、末尾の空白）が入ったまま送られた: 500 ではなく 400 を返し、何も INSERT しない。Task 6 にテストがある。
- 説明に 2048 文字を超える文字列や改行が入った: 2048 文字を超えたら 400。改行とタブは空白 1 つに置き換える。Task 5 にテストがある。

---

## ファイル構成

`~/git/gnucash-quick-expense`（新規、公開リポジトリ `rewse/gnucash-quick-expense`）:

| パス | 役割 |
|---|---|
| `pyproject.toml`、`.python-version`、`uv.lock`、`.gitignore`、`LICENSE` | プロジェクト定義 |
| `src/gnucash_quick_expense/__init__.py` | `__version__` |
| `src/gnucash_quick_expense/money.py` | 金額の解釈、分子・分母への変換、換算と丸め |
| `src/gnucash_quick_expense/config.py` | `config.yaml` の読み込みとアカウントのパターン照合 |
| `src/gnucash_quick_expense/accounts.py` | `accounts` 表からのパス作成と候補の絞り込み |
| `src/gnucash_quick_expense/rates.py` | 公表相場ページの取得と解析、`prices` 表への代替 |
| `src/gnucash_quick_expense/ledger.py` | INSERT する行の組み立てと INSERT |
| `src/gnucash_quick_expense/db.py` | 接続設定と接続、認証失敗の判別 |
| `src/gnucash_quick_expense/app.py` | Starlette のアプリ、API、セキュリティヘッダー |
| `src/gnucash_quick_expense/cli.py` | 起動の入口（`gnucash-quick-expense` コマンド） |
| `src/gnucash_quick_expense/static/index.html`、`app.js`、`app.css` | 画面 |
| `tests/` | pytest。`tests/fixtures/` に公表相場ページの HTML、`tests/integration/` に PostgreSQL を使うテスト |
| `config.example.yaml`、`README.md`、`AGENTS.md`、`.pre-commit-config.yaml`、`.github/` | 文書と CI |

`~/git/ansible-playbooks`: `roles/gnucash_quick_expense/` を新規作成し、`home-primary.yml` と `tests/test_gnucash_quick_expense.py` を変える。

`~/git/cloudfront-waf`、`~/git/security-agent`: 名前の一覧に `expense` を足す。

---

### Task 1: プロジェクトの骨組みと金額の扱い

**Files:**
- Create: `pyproject.toml`、`.python-version`、`.gitignore`、`LICENSE`、`src/gnucash_quick_expense/__init__.py`、`src/gnucash_quick_expense/money.py`、`.pre-commit-config.yaml`
- Test: `tests/test_money.py`

**Interfaces:**
- Produces:
  - `money.AmountError(ValueError)`
  - `money.Rational(NamedTuple)`: `num: int`、`denom: int`
  - `money.parse_amount(text: str, fraction: int) -> money.Rational`。`fraction` は `commodities.fraction`（JPY は 1、USD は 100）。
  - `money.to_decimal(value: money.Rational) -> decimal.Decimal`
  - `money.convert(amount: decimal.Decimal, rate: decimal.Decimal, fraction: int) -> money.Rational`。`amount × rate` を `fraction` の単位で `ROUND_HALF_UP` に丸める。
  - `money.format_amount(value: money.Rational) -> str`。`Rational(123450, 100)` は `"1234.50"`、`Rational(1200, 1)` は `"1200"`。

- [ ] **Step 1: リポジトリを用意する**

`~/git/gnucash-quick-expense` は設計書と計画のコミットだけがあるローカルリポジトリ。`pyproject.toml` は `~/git/stock-price-fetcher/pyproject.toml` の形に合わせ、次の値にする。`name = "gnucash-quick-expense"`、`version = "0.1.0"`、`requires-python = ">=3.12"`、`license = { text = "MIT" }`、`dependencies` は `httpx`、`psycopg[binary]`、`pyyaml`、`starlette`、`uvicorn`（アルファベット順、下限は lock 時点の版）、`[project.optional-dependencies] test = ["pytest"]`、`[project.scripts] gnucash-quick-expense = "gnucash_quick_expense.cli:main"`、build backend は `uv_build`、`[tool.uv] exclude-newer = "4 days"` と、enecoq-data-fetcher と同じ形の `exclude-newer-package = { gnucash-quick-expense = false }`、`[tool.pytest.ini_options]`、`[tool.basedpyright] typeCheckingMode = "standard"`、`[tool.ruff.lint.isort]`（`force-single-line = true`、`single-line-exclusions = ["collections.abc", "typing"]`）。静的ファイルが wheel に入るようにする。`.python-version` は `3.14`。`.gitignore` は stock-price-fetcher のものを写す。`LICENSE` は enecoq-data-fetcher の MIT ライセンスを写し、年を 2026 にする。`.pre-commit-config.yaml` は `git -C ~/git/enecoq-data-fetcher show origin/main:.pre-commit-config.yaml` から shellcheck を除いたもの（actionlint、check-dependabot、zizmor、ruff-check、ruff-format、basedpyright）。

- [ ] **Step 2: 失敗するテストを書く**

```python
# tests/test_money.py
import decimal

import pytest

from gnucash_quick_expense import money


@pytest.mark.parametrize(
    ("text", "fraction", "expected"),
    [
        ("1200", 1, money.Rational(1200, 1)),
        (" 1200 ", 1, money.Rational(1200, 1)),
        ("12.5", 100, money.Rational(1250, 100)),
        ("12.50", 100, money.Rational(1250, 100)),
        ("0.01", 100, money.Rational(1, 100)),
        ("3965", 100, money.Rational(396500, 100)),
    ],
)
def test_parse_amount_accepts(text, fraction, expected):
    assert money.parse_amount(text, fraction) == expected


@pytest.mark.parametrize(
    ("text", "fraction"),
    [
        ("", 1), ("0", 1), ("0.00", 100), ("-5", 1), ("+5", 1), ("1e3", 1),
        (".5", 100), ("5.", 100), ("1.5", 1), ("1.234", 100), ("1,200", 1),
        ("１２００", 1), ("NaN", 1), ("Infinity", 1), ("12 34", 1),
    ],
)
def test_parse_amount_rejects(text, fraction):
    with pytest.raises(money.AmountError):
        money.parse_amount(text, fraction)


def test_convert_rounds_half_up_to_the_target_fraction():
    rate = decimal.Decimal("157.54")
    assert money.convert(decimal.Decimal("1.00"), rate, 1) == money.Rational(158, 1)
    # 3965.00 TWD at 4.87 JPY is 19309.55 JPY.
    assert money.convert(decimal.Decimal("3965.00"), decimal.Decimal("4.87"), 1) == money.Rational(19310, 1)
    assert money.convert(decimal.Decimal("10"), decimal.Decimal("0.125"), 100) == money.Rational(125, 100)


def test_format_amount():
    assert money.format_amount(money.Rational(123450, 100)) == "1234.50"
    assert money.format_amount(money.Rational(1200, 1)) == "1200"
```

- [ ] **Step 3: テストが失敗することを確かめる**

Run: `XDG_CONFIG_HOME=$(mktemp -d /tmp/uvcfg.XXXXXX) uv lock && uv sync --extra test && uv run pytest tests/test_money.py`
Expected: `money` が無いことによる `ImportError` で FAIL

- [ ] **Step 4: `money.py` を実装する**

`parse_amount` は前後の空白を落とした後、`re.ASCII` 付きの正規表現 `^[0-9]+(\.[0-9]+)?$` に一致するものだけを受け付けて `decimal.Decimal` に変換する。小数の桁数が `fraction` の桁数（`len(str(fraction)) - 1`）を超えるか、値が 0 以下ならエラーにする。`fraction` は 10 の累乗だけを受け付ける。

- [ ] **Step 5: テストが通ることを確かめる**

Run: `uv run pytest tests/test_money.py`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add .gitignore .pre-commit-config.yaml .python-version LICENSE pyproject.toml uv.lock src tests
git commit -m "feat(money): parse amounts into GnuCash rationals"
```

### Task 2: 設定ファイルとアカウントのパターン

**Files:**
- Create: `src/gnucash_quick_expense/config.py`、`config.example.yaml`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces:
  - `config.ConfigError(ValueError)`
  - `config.AccountChoice(NamedTuple)`: `patterns: tuple[str, ...]`、`default: str | None`
  - `config.Config(NamedTuple)`: `from_accounts: config.AccountChoice`、`to_accounts: config.AccountChoice`
  - `config.load(path: pathlib.Path) -> config.Config`（`yaml.safe_load`）
  - `config.matches(pattern: str, path: str) -> bool`

`config.example.yaml` の形（値は個人のものでない例にする）:

```yaml
# Accounts offered in the From list. "*" matches one account name and "**"
# matches one or more, so "Assets:**:Cash" matches "Assets:Current Assets:Cash".
from_accounts:
  patterns:
    - "Assets:**:Cash"
  default: "Assets:Current Assets:Cash"
to_accounts:
  patterns:
    - "Expenses:**"
  default: "Expenses:Dining"
```

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_config.py
import pathlib

import pytest

from gnucash_quick_expense import config


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("Assets:**:Cash", "Assets:Yen:Cash", True),
        ("Assets:**:Cash", "Assets:Yen:Cash:Glovebox", False),
        ("Assets:**:Glovebox", "Assets:Yen:Cash:Glovebox", True),
        ("Assets:**:Transit Card", "Assets:Yen:Prepaid:Transit Card", True),
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
    loaded = config.load(pathlib.Path("config.example.yaml"))
    assert loaded.from_accounts.patterns == ("Assets:**:Cash",)
    assert loaded.to_accounts.default == "Expenses:Dining"


@pytest.mark.parametrize(
    "text",
    [
        "from_accounts: {patterns: []}\nto_accounts: {patterns: ['Expenses:**']}\n",
        "to_accounts: {patterns: ['Expenses:**']}\n",
        "from_accounts: {patterns: ['A:**']}\nto_accounts: {patterns: 'Expenses:**'}\n",
        "- not a mapping\n",
    ],
)
def test_load_rejects_invalid_files(tmp_path, text):
    path = tmp_path / "config.yaml"
    path.write_text(text)
    with pytest.raises(config.ConfigError):
        config.load(path)
```

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_config.py`
Expected: `ImportError` で FAIL

- [ ] **Step 3: `config.py` と `config.example.yaml` を実装する**

`matches` はパターンとパスを `:` で区切り、`*` は 1 要素、`**` は 1 要素以上、それ以外は大文字小文字を区別した完全一致とする。`default` は省略でき、省略時は `None`。

- [ ] **Step 4: テストが通ることを確かめる**

Run: `uv run pytest tests/test_config.py`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add config.example.yaml src/gnucash_quick_expense/config.py tests/test_config.py
git commit -m "feat(config): load account patterns from YAML"
```

### Task 3: アカウント一覧

**Files:**
- Create: `src/gnucash_quick_expense/accounts.py`
- Test: `tests/test_accounts.py`、`tests/integration/conftest.py`、`tests/integration/schema.sql`、`tests/integration/test_accounts_db.py`

**Interfaces:**
- Consumes: `config.AccountChoice`、`config.matches`
- Produces:
  - `accounts.Account(NamedTuple)`: `guid: str`、`path: str`（`Root Account:` を除いたパス）、`commodity_guid: str`、`mnemonic: str`、`fraction: int`、`usable: bool`（自分の `placeholder` と `hidden` がどちらも 0）
  - `accounts.fetch_all(conn: psycopg.Connection) -> list[accounts.Account]`
  - `accounts.choose(all_accounts: list[accounts.Account], choice: config.AccountChoice) -> list[accounts.Account]`。使えるものだけを、パスのアルファベット順で返す。
  - `accounts.default_path(choices: list[accounts.Account], choice: config.AccountChoice) -> str | None`。既定のパスが候補に無ければ `None`。
  - `tests/integration/conftest.py` の fixture `gnucash_db`: 環境変数 `GQE_TEST_DATABASE_URL` が無ければ skip。あれば `schema.sql` を流し、接続を返す。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_accounts.py` で `choose` と `default_path` を `Account` のリストでテストする。placeholder の `Assets:Yen`、hidden の `Expenses:Old`、`Assets:Dollar:Cash`、`Assets:Yen:Cash`、`Expenses:Food:Dining` を入れる。`choose(..., AccountChoice(("Assets:**:Cash",), None))` のパスが `["Assets:Yen:Cash", "Assets:Dollar:Cash"]` になること、`Expenses:Old` と placeholder が出ないこと、候補に無い既定値で `default_path` が `None` を返すことを assert する。

`tests/integration/schema.sql` には GnuCash の `accounts`、`commodities`、`prices`、`transactions`、`splits` の CREATE TABLE（列と型は gnucash-import-agent の `.kiro/skills/gnucash-import/references/gnucash-schema.md` と <https://wiki.gnucash.org/wiki/SQL> に合わせる。`guid` は `char(32)` の主キー）を書く。データは `Root Account`、`Assets`、`Assets:Yen`（placeholder）、`Assets:Yen:Cash`（JPY）、`Assets:Dollar:Cash`（USD）、`Assets:NT Dollar:Cash`（TWD）、`Expenses`、`Expenses:Food`、`Expenses:Food:Dining`（JPY）、hidden の `Expenses:Old`、もう 1 つの `parent_guid IS NULL` の行 `Template Root` と、JPY（fraction 1）、USD、TWD（fraction 100）の commodities、TWD から JPY への price 1 件（`date` 2026-08-06 10:59:00、`value_num` 487、`value_denom` 100）と、JPY から USD への逆向きの price 1 件（`date` 2026-07-31 10:59:00、`value_num` 1、`value_denom` 150）。

`tests/integration/test_accounts_db.py` は `fetch_all(gnucash_db)` のパスに `"Assets:Dollar:Cash"` があり、`Root Account` と `Template Root` で始まるパスが無く、USD の `fraction` が 100 であることを assert する。

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_accounts.py`
Expected: `ImportError` で FAIL

- [ ] **Step 3: `accounts.py` を実装する**

`fetch_all` は設計書の再帰 CTE（`name::text` で始め、`Root Account` という名前の `parent_guid IS NULL` の行の子から辿る）に `commodities` を JOIN した 1 本の SELECT にする。

- [ ] **Step 4: 単体テストと結合テストを通す**

Run: `uv run pytest tests/test_accounts.py`
Expected: PASS

結合テストは PostgreSQL 16 のコンテナで流す（macOS では `container`）:

```bash
container run -d --name gqe-pg -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16
GQE_TEST_DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/postgres uv run pytest tests/integration
container stop gqe-pg && container rm gqe-pg
```

Expected: PASS（環境変数が無いときは skip）

- [ ] **Step 5: コミット**

```bash
git add src/gnucash_quick_expense/accounts.py tests/test_accounts.py tests/integration
git commit -m "feat(accounts): build account paths and filter choices"
```

### Task 4: 為替レート

**Files:**
- Create: `src/gnucash_quick_expense/rates.py`
- Test: `tests/test_rates.py`、`tests/fixtures/murc-2026-10-30.html`、`tests/integration/test_rates_db.py`

**Interfaces:**
- Produces:
  - `rates.Quote(NamedTuple)`: `rate: decimal.Decimal`（1 通貨単位あたりの円）、`date: datetime.date`、`source: str`（`"MUFG TTM"` か `"GnuCash price"`）
  - `rates.parse_page(html: str) -> dict[str, decimal.Decimal]`。通貨コードから 1 通貨単位あたりの TTM。
  - `class rates.MurcClient`: `__init__(self, client: httpx.AsyncClient, max_days_back: int = 7)`、`async def ttm(self, currency: str, on: datetime.date) -> rates.Quote | None`
  - `rates.gnucash_price(conn: psycopg.Connection, commodity_guid: str, currency_guid: str, on: datetime.date) -> rates.Quote | None`

公表相場ページの性質（2026-10-31 に確認）:

- URL は `https://www.murc-kawasesouba.jp/fx/past_3month_result.php?y=2026&m=10&d=30`（月と日はゼロ埋めしない）。本文は Shift_JIS なので `cp932` で decode する（meta の EUC-JP は誤り）。
- 土日祝日など表が無い日は HTTP 302 で `past_3month.php?caution=1` に redirect する。redirect は追わず、その日は無いと扱う。
- 表は `<table class="data-table5">` で、各行の `<td>` は英語名、日本語名、コード、TTS、TTB、TTM の順。
- 100 通貨単位の通貨は、表の前にある `以下通貨のみ100通貨単位の円相場です。` の次の `<strong>` に、日本語名が `､` 区切りで書いてある（例: `インドネシア･ルピア､韓国ウォン`）。日本語名で行と照合し、TTM を 100 で割る。
- TWD と MOP は載っていない。

- [ ] **Step 1: fixture を保存する**

```bash
curl -sS -A 'Mozilla/5.0' 'https://www.murc-kawasesouba.jp/fx/past_3month_result.php?y=2026&m=10&d=30' -o tests/fixtures/murc-2026-10-30.html
```

- [ ] **Step 2: 失敗するテストを書く**

```python
# tests/test_rates.py (excerpt)
def test_parse_page_reads_ttm_per_unit():
    html = (FIXTURES / "murc-2026-10-30.html").read_bytes().decode("cp932")
    table = rates.parse_page(html)
    assert table["USD"] == decimal.Decimal("157.54")
    assert table["KRW"] == decimal.Decimal("0.1177")
    assert "TWD" not in table


def test_parse_page_returns_empty_for_unexpected_html():
    assert rates.parse_page("<html><body>maintenance</body></html>") == {}
```

`MurcClient` は `httpx.MockTransport` でテストする。

- `test_ttm_walks_back_to_the_last_business_day`: 10/31 には 302、10/30 には fixture を返す。`ttm("USD", date(2026, 10, 31))` が `Quote(Decimal("157.54"), date(2026, 10, 30), "MUFG TTM")` になる。
- `test_ttm_gives_up_after_max_days_back`: すべて 302 なら `None`。要求の回数が `max_days_back + 1` 回。
- `test_ttm_returns_none_for_unpublished_currency`: `ttm("TWD", ...)` が `None`。
- `test_ttm_returns_none_when_the_site_fails`: transport が `httpx.ConnectTimeout` を投げても、HTTP 500 を返しても `None`。
- `test_ttm_caches_past_days`: 過去の同じ日付で 2 回呼んでも要求は 1 回。JST の今日に表が無かった結果はキャッシュしない（公表前でも後で取れるようにする）。

`tests/integration/test_rates_db.py`: Task 3 の schema の TWD 価格で、`gnucash_price(conn, twd_guid, jpy_guid, date(2026, 10, 31))` が `Quote(Decimal("4.87"), date(2026, 8, 6), "GnuCash price")` になり、`date(2026, 8, 5)` では `None` になる。逆向きの price（JPY から USD へ、`date` 2026-07-31 10:59:00、`value_num` 1、`value_denom` 150）だけがある USD では、`gnucash_price(conn, usd_guid, jpy_guid, date(2026, 10, 31))` の `rate` が `Decimal("150")` になる。

- [ ] **Step 3: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_rates.py`
Expected: `ImportError` で FAIL

- [ ] **Step 4: `rates.py` を実装する**

HTML の解析は標準ライブラリの `html.parser.HTMLParser` で行い、依存を増やさない。`MurcClient` の要求は `follow_redirects=False`、タイムアウト 5 秒。今日の判定は `zoneinfo.ZoneInfo("Asia/Tokyo")` で行う。`gnucash_price` は `prices` から、`date` が `on` の翌日 00:00 より前の行のうち、`commodity_guid` から `currency_guid` への向きの行と、その逆向きの行を合わせて最新の 1 件を選ぶ。GnuCash デスクトップ版も逆向きの price を使って換算するため。順向きなら `value_num / value_denom`、逆向きなら `value_denom / value_num` を Decimal で返す。

- [ ] **Step 5: テストを通す**

Run: `uv run pytest tests/test_rates.py`、Task 3 の手順で `tests/integration`
Expected: PASS

- [ ] **Step 6: コミット**

```bash
git add src/gnucash_quick_expense/rates.py tests/test_rates.py tests/fixtures tests/integration/test_rates_db.py
git commit -m "feat(rates): read MUFG TTM with a GnuCash price fallback"
```

### Task 5: 取引の組み立てと INSERT

**Files:**
- Create: `src/gnucash_quick_expense/ledger.py`
- Test: `tests/test_ledger.py`、`tests/integration/test_ledger_db.py`

**Interfaces:**
- Consumes: `accounts.Account`、`money.Rational`
- Produces:
  - `ledger.EntryError(ValueError)`
  - `ledger.Expense(NamedTuple)`: `post_date: datetime.date`、`description: str`、`from_account: accounts.Account`、`to_account: accounts.Account`、`amount: money.Rational`（`from_account` の通貨）、`to_quantity: money.Rational`（`to_account` の commodity。通貨が同じなら `amount` と同じ）
  - `ledger.clean_description(text: str) -> str`。前後の空白を落とし、改行とタブを空白 1 つにする。2048 文字を超えたら `EntryError`。
  - `ledger.build(expense: ledger.Expense, now: datetime.datetime) -> tuple[dict[str, object], list[dict[str, object]]]`。transactions の 1 行と splits の 2 行（減額側、増額側の順）を列名の dict で返す。日時は UTC の aware な datetime。
  - `ledger.insert(conn: psycopg.Connection, expense: ledger.Expense) -> str`。1 トランザクションで INSERT し、transaction の GUID を返す。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_ledger.py`:

- `test_build_same_currency`: JPY の Cash から JPY の Dining へ 1200 円。transactions の `currency_guid` が Cash の `commodity_guid`、`post_date` が `datetime(2026, 10, 30, 10, 59, tzinfo=datetime.UTC)`、`num` と `description` が `""`。splits の `value_num` と `quantity_num` が `-1200` と `1200`、分母はすべて 1、`reconcile_state` がすべて `"n"`、`reconcile_date` と `lot_guid` が `None`、`memo` と `action` が `""`。3 つの GUID が 32 文字の小文字 16 進数で、すべて違う。
- `test_build_foreign_cash`: USD の Cash から JPY の Dining へ `Rational(1250, 100)`、`to_quantity` が `Rational(1969, 1)`。減額側は value と quantity が `-1250/100`、増額側は value が `1250/100`、quantity が `1969/1`。
- `test_clean_description`: `"  Lunch\nwith\tA "` が `"Lunch with A"`。2049 文字で `EntryError`、2048 文字は通る。

`tests/integration/test_ledger_db.py`: `insert` の後、`transactions` が 1 行、その GUID の `splits` が 2 行あり、value の合計が 0 で、`post_date` が `2026-10-30 10:59:00` として読める。

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_ledger.py`
Expected: `ImportError` で FAIL

- [ ] **Step 3: `ledger.py` を実装する**

GnuCash の `timestamp` 列は UTC の値をタイムゾーン無しで持つので、INSERT するときは UTC の naive な値にする。セッションのタイムゾーンに頼らないよう、`insert` のトランザクションの最初に `SET LOCAL TIME ZONE 'UTC'` を実行する。SQL は psycopg のパラメータで渡す。

- [ ] **Step 4: テストを通す**

Run: `uv run pytest tests/test_ledger.py`、Task 3 の手順で `tests/integration`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/gnucash_quick_expense/ledger.py tests/test_ledger.py tests/integration/test_ledger_db.py
git commit -m "feat(ledger): insert a two-split expense transaction"
```

### Task 6: DB 接続と API

**Files:**
- Create: `src/gnucash_quick_expense/db.py`、`src/gnucash_quick_expense/app.py`、`src/gnucash_quick_expense/cli.py`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: Task 1〜5 のすべて
- Produces:
  - `db.Settings(NamedTuple)`: `host: str`、`port: int`、`dbname: str`、`sslmode: str`、`sslrootcert: str | None`。`db.Settings.from_env(environ: Mapping[str, str]) -> db.Settings` は `GQE_DB_HOST`、`GQE_DB_PORT`（既定 5432）、`GQE_DB_NAME`、`GQE_DB_SSLMODE`（既定 `require`）、`GQE_DB_SSLROOTCERT` を読む。
  - `db.AuthError(Exception)`、`db.connect(settings: db.Settings, user: str, password: str) -> psycopg.Connection`。SQLSTATE `28P01` と `28000` を `AuthError` にする。`connect_timeout` は 10 秒、`application_name` は `gnucash-quick-expense`。
  - `app.create_app(cfg: config.Config, settings: db.Settings, connect: Callable[[db.Settings, str, str], psycopg.Connection] = db.connect, murc: rates.MurcClient | None = None) -> starlette.applications.Starlette`
  - `cli.main() -> None`: `--host`（既定 `127.0.0.1`）、`--port`（既定 8082）、`--config`（既定は環境変数 `GQE_CONFIG`）を受け取り、`uvicorn.run(..., access_log=False, proxy_headers=False)` で起動する。

API（すべて `POST`、`Content-Type: application/json` 以外は 415、本文は 16 KiB まで）:

| パス | 本文 | 応答 |
|---|---|---|
| `/api/accounts` | `{"username", "password"}` | `{"from": [{"path", "currency"}], "to": [{"path", "currency"}], "from_default", "to_default"}` |
| `/api/rate` | `{"username", "password", "from", "to", "date", "amount"}` | `{"to_amount": str \| null, "rate": str \| null, "rate_date": str \| null, "source": str \| null}`。通貨が同じなら 400 |
| `/api/expenses` | `{"username", "password", "from", "to", "date", "description", "amount", "to_amount"}` | `{"guid", "date", "amount", "currency", "from", "to", "to_amount", "to_currency"}`。`to_amount` は通貨が違うときだけ必須 |

`/api/rate` は、増額側が JPY のときだけ `MurcClient.ttm` を試し、`None` なら `rates.gnucash_price` を試す。増額側が JPY 以外なら `gnucash_price` だけを試す。どちらも無ければ値はすべて `null`。`to_amount` は `money.convert` の結果を `money.format_amount` で文字列にしたもの。`date` は `YYYY-MM-DD` で、それ以外は 400。

`GET /` は `static/index.html` を返し、`GET /static/{name}` は静的ファイルを返す。`index.html` の中の静的ファイルの URL に、起動時に計算した内容のハッシュを `?v=` で付け、静的ファイルには `Cache-Control: public, max-age=31536000, immutable` を付ける。`GET /` と API は `Cache-Control: no-store`。すべての応答に `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`、`X-Content-Type-Options: nosniff`、`Referrer-Policy: no-referrer` を付ける。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_app.py` は `starlette.testclient.TestClient` と、`connect` に渡す偽の関数でテストする。偽の `connect` はユーザー名 `bad` で `db.AuthError` を投げ、それ以外は何もしない接続オブジェクトを返す。`accounts.fetch_all`、`ledger.insert`、`rates.gnucash_price` は `monkeypatch` で置き換え、`fetch_all` は Task 3 の schema と同じ口座を返す。`murc` には `ttm` を差し替えた偽物を渡す。

- `test_accounts_returns_choices_and_defaults`: パスと通貨、既定値が返る。`Root Account:` で始まるものが無い。
- `test_wrong_password_is_401`: 3 つの API すべてで 401。応答の本文にパスワードが含まれない。
- `test_non_json_is_415`: `application/x-www-form-urlencoded` で 415。
- `test_unknown_to_account_is_400_and_inserts_nothing`: `"to": "expenses:foods:dining"` と `"to": "Expenses:Food:Dining "` で 400、`ledger.insert` が呼ばれない。
- `test_foreign_expense_requires_to_amount`: USD の Cash から Dining へ、`to_amount` 無しで 400。`"1969"` 付きで 200 になり、`ledger.insert` に `to_quantity == Rational(1969, 1)` が渡る。
- `test_rate_falls_back_to_gnucash_price`: `ttm` が `None`、`gnucash_price` が `Quote(Decimal("4.87"), date(2026, 8, 6), "GnuCash price")` のとき、TWD 3965 で `{"to_amount": "19310", "rate": "4.87", "rate_date": "2026-08-06", "source": "GnuCash price"}`。
- `test_rate_uses_gnucash_price_when_the_site_fails`: 偽の `murc` に、`httpx.ConnectTimeout` を投げる `MockTransport` を持たせた本物の `rates.MurcClient` を渡す。`gnucash_price` が USD の `Quote(Decimal("150"), date(2026, 7, 31), "GnuCash price")` を返すとき、USD 12.50 で 200 になり、`to_amount` が `"1875"`、`source` が `"GnuCash price"`。
- `test_rate_is_empty_only_without_any_rate`: `ttm` も `gnucash_price` も `None` のとき、200 で値がすべて `null`。
- `test_invalid_date_is_400`: `"2026-02-30"` と `"2026/10/30"` で 400。
- `test_security_headers`: `GET /` と API の応答に CSP、`nosniff`、`no-referrer` が付き、`GET /` と API は `no-store`。
- `test_logs_do_not_contain_credentials`: `caplog` で全 API を呼んだ後、ログにパスワードの文字列が無い。

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_app.py`
Expected: `ImportError` で FAIL

- [ ] **Step 3: `db.py`、`app.py`、`cli.py` を実装する**

DB の処理は同期の psycopg なので、ハンドラーからは `starlette.concurrency.run_in_threadpool` で呼ぶ。接続はリクエストごとに開いて閉じ、プールは持たない。クライアントから受け取ったパスは、`accounts.choose` の結果と完全一致で照合して `Account` を得る。GUID はクライアントから受け取らない。

- [ ] **Step 4: テストを通す**

Run: `uv run pytest`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add src/gnucash_quick_expense/db.py src/gnucash_quick_expense/app.py src/gnucash_quick_expense/cli.py tests/test_app.py
git commit -m "feat(app): serve the account, rate, and expense APIs"
```

### Task 7: 画面

**Files:**
- Create: `src/gnucash_quick_expense/static/index.html`、`app.js`、`app.css`
- Test: `tests/test_static.py`

**Interfaces:**
- Consumes: Task 6 の API と静的ファイルの配信

画面の動き（文言はすべて英語）:

1. 最初は `Username`（`autocomplete="username"`）、`Password`（`autocomplete="current-password"`）、`Sign in` だけが使える。
2. `/api/accounts` が成功したら入力欄を有効にする。`Date` は端末の今日（`<input type="date">`）、`Description` は空、`From` は `<select>` で既定値を選ぶ。`To` はテキスト欄と自前のコンボボックス（入力した文字列で、大文字小文字を区別せずに部分一致で絞り込む。`role="combobox"` と `role="listbox"` を付ける）で、既定値を入れておく。`To` が候補と完全一致しない間は `Add` を押せない。
3. `From` と `To` の通貨が違うときだけ、`Amount in <To の通貨>` 欄と、出どころの表示（例: `MUFG TTM, 2026-10-30`、`GnuCash price, 2026-08-06`、`No rate found. Enter the amount.`）を出す。金額、日付、`From`、`To` が変わったら `/api/rate` を呼び直し、手入力の値も上書きする。
4. `Amount` は `inputmode="decimal"`。送信前と `/api/rate` を呼ぶ前に、値を `normalize("NFKC")` で半角にし、`,` を取り除く。数値には変換しない。`Amount in …` も同じ扱いにする。
5. `Add` で `/api/expenses` に送る。成功したら `Added: 2026-10-30, 12.50 USD, <From> → <To>` の形で表示し、パスワード、金額、説明、`Amount in …` を空にして、入力欄を無効に戻す（次の入力はもう一度 `Sign in` から）。401 なら `Wrong username or password.`、400 なら応答のメッセージ、そのほかは `Could not add the expense. Try again.` を出す。
6. インラインの `<script>` と `style` 属性は使わない（CSP のため）。外部のフォントや CDN は読み込まない。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_static.py` は次を assert する。

- `index.html` の `<script>` はすべて `src` 付きで中身が無く、`style=` 属性と `http://`、`https://` の参照が無い。`autocomplete="username"` と `autocomplete="current-password"` がある。
- `app.js` に `normalize("NFKC")` がある。`parseFloat`、`Number(`、`localStorage`、`sessionStorage`、`document.cookie` が無い。

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run pytest tests/test_static.py`
Expected: ファイルが無いことによる FAIL

- [ ] **Step 3: 画面を実装する**

スマートフォンの縦画面で片手で操作できる 1 列のレイアウトにする。iOS Safari が拡大しないよう、入力欄の文字は 16px 以上にする。

- [ ] **Step 4: テストを通し、ブラウザで確かめる**

Run: `uv run pytest`
Expected: PASS

Task 3 の PostgreSQL コンテナに `schema.sql` を流し、`mktemp -d /tmp/gqe-ui.XXXXXX` の run ディレクトリに、パターン `Assets:**:Cash` と `Expenses:**`、既定値 `Assets:Yen:Cash` と `Expenses:Food:Dining` の設定ファイルを作る。`GQE_DB_HOST=127.0.0.1 GQE_DB_PORT=55432 GQE_DB_NAME=postgres GQE_DB_SSLMODE=disable uv run gnucash-quick-expense --config <その設定ファイル>` で起動し、agent-browser（iPhone の画面サイズ）で次を確かめる。サインインできる。`To` が部分一致で絞り込める。全角の `１，２００` が `1200` として入る。USD の Cash を選ぶと `Amount in JPY` が出て、TWD では `GnuCash price, 2026-08-06` が出る。`Add` で行が入る（`psql` で確認）。開発者ツールのコンソールに CSP の違反が出ない。

- [ ] **Step 5: コミット**

```bash
git add src/gnucash_quick_expense/static tests/test_static.py
git commit -m "feat(web): add the mobile expense form"
```

### Task 8: 文書と CI

**Files:**
- Create: `README.md`、`AGENTS.md`、`.github/dependabot.yml`、`.github/workflows/dependabot-review.yml`、`dependency-scan.yml`、`gitleaks.yml`、`lint.yml`、`test.yml`、`trufflehog.yml`

- [ ] **Step 1: `.github` を作る**

`~/git/enecoq-data-fetcher` の origin/main（`git -C ~/git/enecoq-data-fetcher show origin/main:.github/<file>`）から写す。ローカルの clone は Dependabot のブランチにあるので、作業ツリーのファイルは使わない。`release.yml` は作らない。`dependabot.yml` は github-actions（`rewse/*` を cooldown から除外）、uv、pre-commit の 3 エントリ。`test.yml` の `Run tests` は `uv run --extra test pytest` にし、結合テスト用に `services: postgres`（`postgres:16` をダイジェストで固定し、ヘルスチェックを付ける）と `GQE_TEST_DATABASE_URL` を足す。`gitleaks.yml`、`trufflehog.yml`、`dependency-scan.yml` の cron の分は、`rg -n "cron:" ~/git/*/.github/workflows` で他のリポジトリと重ならない値を選ぶ。trufflehog の `--exclude-detectors` は誤検知が出るまで付けない。

- [ ] **Step 2: `README.md` と `AGENTS.md` を書く**

README は英語で、最初の段落に「支出を 1 件追加するだけのフォームで、GnuCash のすべての機能を提供するものではない」ことを書く。続けて、必要なもの（GnuCash の PostgreSQL バックエンドと、権限を絞った専用ロール。例として設計書の GRANT 文）、設定（`config.example.yaml`、環境変数 `GQE_CONFIG` と `GQE_DB_*`）、起動方法、リバースプロキシで TLS を終端する前提、セキュリティ上の注意（資格情報はリクエストごとに送られ保存されない、ログイン失敗は 401）を書く。個人のアカウント名やホスト名は書かない。`AGENTS.md` は enecoq-data-fetcher のものにならい、製品の説明、開発コマンド、結合テストの流し方、依存とセキュリティ、コミットのスコープ、検証手順を書く。書き終えたら `~/.agents/skills/humanizer/SKILL.md` に沿って README を見直す。

- [ ] **Step 3: lint とテストを通す**

Run: `git add -A && uvx --with pre-commit-uv==4.3.0 pre-commit@4.6.2 run --all-files && uv run --extra test pytest && osv-scanner --lockfile=uv.lock`
Expected: すべて成功。フックが整形したファイルがあれば add し直す。

- [ ] **Step 4: コミット**

```bash
git add README.md AGENTS.md .github
git commit -m "docs: add README, AGENTS.md, and CI workflows"
```

### Task 9: GitHub に公開する

外部への書き込みなので、実行する前にユーザーに確認する。

- [ ] **Step 1: 公開リポジトリを作って push する**

```bash
gh repo create rewse/gnucash-quick-expense --public --source ~/git/gnucash-quick-expense --push --description "A mobile web form that adds one expense to a GnuCash PostgreSQL database"
```

- [ ] **Step 2: CI を確かめる**

Run: `gh run list -R rewse/gnucash-quick-expense --limit 10 | cat`
Expected: Lint、Test、Gitleaks、Dependency Scan が success。失敗したら直して push し直す。

- [ ] **Step 3: リポジトリの設定をそろえる**

`gh api repos/rewse/enecoq-data-fetcher | cat` と比べ、Dependabot のセキュリティ更新、secret scanning、push protection をそろえる。`dependabot-review.yml` が使う secrets（`DEPENDABOT_APP_CLIENT_ID`、`DEPENDABOT_APP_PRIVATE_KEY`、`KIRO_API_KEY`）は値を扱えないので、ユーザーに設定を頼む。

### Task 10: ansible-playbooks のロール

**Files:**
- Create: `roles/gnucash_quick_expense/{files,handlers,meta,tasks,templates,vars}/...`
- Modify: `home-primary.yml`（サービスの段のアルファベット順で、`filebrowser` の後、`homeassistant` の前）
- Test: `tests/test_gnucash_quick_expense.py`

**Interfaces:**
- Consumes: Task 9 で公開した `https://github.com/rewse/gnucash-quick-expense.git`、`cli.main` の引数、`GQE_*` 環境変数、`config.yaml` の形

`~/git/ansible-playbooks` で `git pull` してから作業し、`AGENTS.md` を読む。`roles/zabbix_money_market/tasks/app.yml`（自分のリポジトリを root 所有で checkout し、環境は checkout の外に置いて `uv sync --frozen`）と `roles/zabbix_mcp`（systemd、Apache、fail2ban）を手本にする。

- `vars/main.yml`: `gnucash_quick_expense_hostname: expense.example.com`、`gnucash_quick_expense_port: 8082`（2026-10-31 に web で空いていることを確認済み）、`gnucash_quick_expense_venv: /var/lib/gnucash-quick-expense/venv`、`gnucash_quick_expense_db_host`、`gnucash_quick_expense_db_port`、`gnucash_quick_expense_db_name`（`op read "op://<vault>/<db-endpoint-item>/server"`、`/port`、`/database` の lookup）、`gnucash_quick_expense_from_accounts`（patterns `Assets:**:Glovebox`、`Assets:**:Cash`、`Assets:**:Transit Card`、default `Assets:Yen:Cash`）、`gnucash_quick_expense_to_accounts`（patterns `Expenses:**`、default `Expenses:Food:Dining`）。
- `tasks/user.yml`: システムユーザー `gnucash-quick-expense`（`/usr/sbin/nologin`）と、そのユーザー所有の `/var/lib/gnucash-quick-expense`、root 所有の `/etc/gnucash-quick-expense`（`0755`）。
- `tasks/app.yml`（tag に `update`）: `https://github.com/rewse/gnucash-quick-expense.git` の `main` を `/opt/gnucash-quick-expense` に root 所有で checkout し、`gnucash-quick-expense` ユーザーで `UV_PROJECT_ENVIRONMENT` を指定して `uv sync --frozen` を実行する。zabbix_money_market と同じく、`changed_when`、check mode の扱い、`safe.directory` と checkout 内の `.venv` の削除を入れる。checkout か sync が変わったらサービスを再起動する。
- `tasks/service.yml`: `templates/config.yaml.j2` を `/etc/gnucash-quick-expense/config.yaml` に、`templates/gnucash-quick-expense.env.j2` を `/etc/gnucash-quick-expense/env` に置く（どちらも `0644`。接続先とアカウントだけで、資格情報を含まない）。env には `GQE_DB_SSLMODE=require` を入れる。RDS の CA バンドルで `verify-ca` が通ることを web で確かめられたら、バンドルを置いて `verify-ca` と `GQE_DB_SSLROOTCERT` にする（ホスト名が CNAME なので `verify-full` は使えない）。systemd ユニット `files/gnucash-quick-expense.service` を置いて有効化する。ユニットは zabbix-mcp-server と同じハードニング（`NoNewPrivileges`、`ProtectSystem=strict`、`ProtectHome`、`PrivateTmp`、`PrivateDevices`、`ProtectKernelTunables`、`ProtectKernelModules`、`ProtectControlGroups`、`RestrictSUIDSGID`、`RestrictNamespaces`）に、`OnFailure=failure-notify@%n.service`、`Restart=on-failure`、`EnvironmentFile=/etc/gnucash-quick-expense/env`、`ExecStart=/var/lib/gnucash-quick-expense/venv/bin/gnucash-quick-expense --host 127.0.0.1 --port 8082 --config /etc/gnucash-quick-expense/config.yaml` を足す。ログは journal に出す。
- `tasks/apache.yml`、`templates/expense.example.com.conf.j2`: filebrowser の vhost と同じ `RequestHeader unset` の 3 行（`X-Forwarded-For`、`X-Forwarded-Host`、`X-Real-IP`）とその理由のコメント、`127.0.0.1` への `ProxyPass`、ワイルドカード証明書。インターネットから使うので `Require ip` は付けない。
- `tasks/fail2ban.yml`、`templates/fail2ban-filter.conf.j2`、`templates/fail2ban-jail.conf.j2`: フィルターと jail の名前は `gnucash-quick-expense`。`failregex = ^{{ gnucash_quick_expense_hostname | regex_escape }}:\d+ <HOST> \S+ \S+ \[\] "POST /api/\S* HTTP/[\d.]+" 401 \d+`。jail は filebrowser と同じく `backend = auto`、`action = %(action_)s` と `apache-deny`、`logpath = /var/log/apache2/other_vhosts_access.log`。
- `meta/main.yml`: `fail2ban`、`httpd` に依存。
- `handlers/main.yml`: `Reload Apache`、`Reload systemd`、`Restart fail2ban` は他のロールと同じ名前と中身。`Restart gnucash-quick-expense` は check mode では実行しない。

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_gnucash_quick_expense.py` は、`tests/test_internet_exposure.py` の `NvrFail2banTest` と同じ書き方（`unittest`、`load_yaml`、`jail`、`filter_regex`、`access_line`）で、次を確かめる。

- fail2ban の component が import され、`meta` に `fail2ban` がある。jail が `other_vhosts_access.log` を `backend = auto` で読む。
- フィルターが `access_line("expense.example.com", "POST /api/accounts", 401)` と `/api/expenses` の 401 に一致し、200、400、`GET /` の 401、別の vhost の 401 には一致しない。
- vhost に 3 つの `RequestHeader unset` があり、`Require ip` が無く、`ProxyPass` の先が `127.0.0.1:{{ gnucash_quick_expense_port }}`。
- env と config のテンプレートに `password` という文字列が無い。
- checkout が root 所有で、環境が checkout の外（`/var/lib/gnucash-quick-expense/venv`）にある。
- `home-primary.yml` にロールがある。

- [ ] **Step 2: テストが失敗することを確かめる**

Run: `uv run --with pytest --with ansible-core pytest tests/test_gnucash_quick_expense.py`
Expected: FAIL

- [ ] **Step 3: ロールを実装する**

- [ ] **Step 4: テストと lint を通す**

Run: `uvx --with pre-commit-uv==4.3.0 pre-commit@4.6.2 run --all-files && uv run --with pytest --with ansible-core pytest tests`
Expected: PASS

- [ ] **Step 5: check mode で流す**

1Password の参照が読めることを `direnv exec . op read op://<vault>/<db-endpoint-item>/server` で確かめてから、`ansible-playbook home-primary.yml --tags gnucash_quick_expense --check --diff` を流す。
Expected: 失敗が無い（初回の checkout が無いことによる skip は報告されてよい）

- [ ] **Step 6: 適用して、2 回目が変化なしになることを確かめる**

Run: `ansible-playbook home-primary.yml --tags gnucash_quick_expense` を 2 回
Expected: 終了コード 0、2 回目は `changed=0`

web で次を確かめる。`curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8082/` が `200`。`curl -sS -o /dev/null -w '%{http_code}\n' -H 'Content-Type: application/json' -d '{"username":"x","password":"y"}' http://127.0.0.1:8082/api/accounts` が `401`。`sudo fail2ban-client status gnucash-quick-expense` で jail が動いている。

- [ ] **Step 7: コミットして push する**

push は外部への書き込みなので、その前にユーザーに確認する。

```bash
git add home-primary.yml roles/gnucash_quick_expense tests/test_gnucash_quick_expense.py
git commit -m "feat(gnucash_quick_expense): deploy the expense form on web"
git push
```

### Task 11: CloudFront、DNS、ペンテスト

外部への書き込みを含むので、各 push とデプロイの前にユーザーに確認する。

- [ ] **Step 1: cloudfront-waf を変える**

`~/git/cloudfront-waf` で `git pull` し、`AGENTS.md` を読む。`0c4a5bf` と同じファイル（`infra/template.yaml` の `Aliases`、`scripts/switch-dns.sh` の `SUBDOMAINS`、`tests/test_template.py`、`tests/test_switch_dns.py`、`README.md` と `docs/setup.md` の名前の一覧と数）に `expense` をアルファベット順で足す。`uv run pytest -q`、`uv run cfn-lint infra/template.yaml`、pre-commit を通して、`feat: serve expense.example.com through CloudFront` でコミットして push する。

- [ ] **Step 2: ユーザーにデプロイを頼む**

`AWS_PROFILE=admin scripts/deploy.sh` と `AWS_PROFILE=admin scripts/switch-dns.sh cloudfront` を、会社の Mac で実行してもらう。

- [ ] **Step 3: UniFi の DNS ポリシーを足す**

ansible-playbooks の `AGENTS.md` の UniFi 節に従い、Site Manager API で `expense.example.com` を `web.example.com` に向ける CNAME の DNS ポリシーを足す。既存の `nas.example.com` のポリシーを読んで同じ形にする。

- [ ] **Step 4: security-agent に毎月のペンテストを足す**

`~/git/security-agent` で `git pull` して `AGENTS.md` を読み、`monthly-nas-rewse-jp` と同じ形で `monthly-expense-rewse-jp` を `targets.toml` と `infra/template.yaml` に足す。実行日時は他と重ならないようにし、対象ドメインの検証まで行う。ペンテストに DB の資格情報を渡さない。

- [ ] **Step 5: 外から確かめる**

Run: `curl -sS -o /dev/null -w '%{http_code}\n' https://expense.example.com/` と `curl -sSI https://expense.example.com/ | rg -i 'x-cache|content-security-policy'`
Expected: `200`、`x-cache` がある（CloudFront を通っている）、CSP がある

### Task 12: 本番での確認

- [ ] **Step 1: 最初の 1 件をユーザーに入れてもらう**

ユーザーにスマートフォンで `https://expense.example.com/` を開いてもらい、1Password の `GnuCash Quick Expense` でサインインして、少額の支出を 1 件入れてもらう。

- [ ] **Step 2: DB で確かめる**

`expense-form` ロールは `transactions` を読めないので、`op://<vault>/<db-endpoint-item>` の `gnucash` ユーザーで読み取り専用（`PGOPTIONS='-c default_transaction_read_only=on'`）に接続する。`enter_date` が最新の取引の `post_date` が `10:59:00`、splits が 2 行で `reconcile_state` が `n`、value の合計が 0 であることを確かめる。結果をユーザーに伝え、GnuCash デスクトップ版で開き直して見えることを確かめてもらう。
