"""Exchange rates into JPY: MUFG's published TTM, then GnuCash's price table.

The MUFG page lists the day's quotes for about 30 currencies on business
days only; on other days it redirects to a notice. A few currencies are
quoted per 100 units, as the note above the table names them.
"""

import datetime
import decimal
import html.parser
import logging
import unicodedata
import zoneinfo
from typing import NamedTuple

import httpx
import psycopg

_URL = "https://www.murc-kawasesouba.jp/fx/past_3month_result.php"
_TOKYO = zoneinfo.ZoneInfo("Asia/Tokyo")
_HUNDRED_UNITS_NOTE = "以下通貨のみ100通貨単位の円相場です"
_TIMEOUT = httpx.Timeout(5.0)

MUFG_TTM = "MUFG TTM"
GNUCASH_PRICE = "GnuCash price"

_log = logging.getLogger(__name__)

# Both directions of a pair, newest first; a price quoted the other way is
# inverted, as GnuCash does when it converts.
_PRICE_SQL = """
SELECT date, value_num, value_denom, commodity_guid = %(commodity)s AS forward
FROM prices
WHERE date < %(before)s
  AND ((commodity_guid = %(commodity)s AND currency_guid = %(currency)s)
    OR (commodity_guid = %(currency)s AND currency_guid = %(commodity)s))
  AND value_num > 0 AND value_denom > 0
ORDER BY date DESC
LIMIT 1
"""


class Quote(NamedTuple):
    """A rate in units of the target currency per unit of the source."""

    rate: decimal.Decimal
    date: datetime.date
    source: str


class _PageParser(html.parser.HTMLParser):
    """Collects the rate table's cells and the per-100-unit currency names.

    The page leaves out most <tr> start tags, so a row is the run of cells
    up to each </tr>.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.hundred_units: set[str] = set()
        self._in_table = False
        self._cell: list[str] | None = None
        self._row: list[str] = []
        self._strong: list[str] | None = None
        self._after_note = False

    def handle_starttag(self, tag, attrs):
        if tag == "table" and "data-table5" in (dict(attrs).get("class") or ""):
            self._in_table = True
        elif tag == "td" and self._in_table:
            self._cell = []
        elif tag == "strong":
            self._strong = []

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._in_table:
            if self._row:
                self.rows.append(self._row)
            self._row = []
        elif tag == "table":
            self._in_table = False
        elif tag == "strong" and self._strong is not None:
            text = unicodedata.normalize("NFKC", "".join(self._strong))
            if self._after_note:
                self.hundred_units = {n.strip() for n in text.split("、") if n.strip()}
                self._after_note = False
            elif unicodedata.normalize("NFKC", _HUNDRED_UNITS_NOTE) in text:
                self._after_note = True
            self._strong = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        if self._strong is not None:
            self._strong.append(data)


def parse_page(page: str) -> dict[str, decimal.Decimal]:
    """Reads TTM per one unit of each currency from a MUFG rate page.

    Returns:
        Currency codes mapped to JPY per unit. Rows whose TTM is not a
        number are left out; a page without the table gives an empty dict.
    """
    parser = _PageParser()
    parser.feed(page)
    parser.close()
    table: dict[str, decimal.Decimal] = {}
    for row in parser.rows:
        if len(row) < 6:
            continue
        name, code, ttm = unicodedata.normalize("NFKC", row[1]), row[2], row[5]
        try:
            rate = decimal.Decimal(ttm)
        except decimal.InvalidOperation:
            continue
        if not rate.is_finite() or rate <= 0:
            continue
        if name in parser.hundred_units:
            rate /= 100
        table[code] = rate
    return table


class MurcClient:
    """Fetches MUFG TTM quotes, walking back over days without quotes."""

    def __init__(self, client: httpx.AsyncClient, max_days_back: int = 7) -> None:
        self._client = client
        self._max_days_back = max_days_back
        self._cache: dict[datetime.date, dict[str, decimal.Decimal]] = {}

    async def ttm(self, currency: str, on: datetime.date) -> Quote | None:
        """Returns the TTM of `on`, or of the latest earlier business day.

        Returns:
            The quote, or None when the currency is not published, no day
            within reach has quotes, or the site cannot be read.
        """
        for back in range(self._max_days_back + 1):
            day = on - datetime.timedelta(days=back)
            table = await self._table(day)
            if table is None:
                return None
            if table:
                rate = table.get(currency)
                return Quote(rate, day, MUFG_TTM) if rate is not None else None
        return None

    async def _table(self, day: datetime.date) -> dict[str, decimal.Decimal] | None:
        """Returns the day's quotes, {} for a day without any, None on failure."""
        if day in self._cache:
            return self._cache[day]
        try:
            response = await self._client.get(
                _URL,
                params={"y": day.year, "m": day.month, "d": day.day},
                follow_redirects=False,
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as e:
            _log.warning("MUFG rates for %s unavailable: %s", day, type(e).__name__)
            return None
        if response.is_redirect:
            table = {}
        elif response.status_code == 200:
            table = parse_page(response.content.decode("cp932", errors="replace"))
            if not table:
                _log.warning("MUFG rate page for %s has no rate table", day)
                return None
        else:
            _log.warning("MUFG rates for %s returned %s", day, response.status_code)
            return None
        # Today's quotes may not be published yet, so only past days are kept.
        if table or day < datetime.datetime.now(_TOKYO).date():
            self._cache[day] = table
        return table


def gnucash_price(
    conn: psycopg.Connection,
    commodity_guid: str,
    currency_guid: str,
    on: datetime.date,
) -> Quote | None:
    """Returns the latest GnuCash price of a commodity on or before a day.

    Args:
        conn: A connection to the GnuCash database.
        commodity_guid: The commodity being converted from.
        currency_guid: The currency being converted to.
        on: The last day whose prices count.

    Returns:
        Units of the currency per unit of the commodity, from the newest
        price in either direction, or None when the table has none.
    """
    before = datetime.datetime.combine(on + datetime.timedelta(days=1), datetime.time())
    with conn.cursor() as cur:
        cur.execute(
            _PRICE_SQL,
            {"commodity": commodity_guid, "currency": currency_guid, "before": before},
        )
        row = cur.fetchone()
    if row is None:
        return None
    date, num, denom, forward = row
    rate = (
        decimal.Decimal(num) / decimal.Decimal(denom)
        if forward
        else decimal.Decimal(denom) / decimal.Decimal(num)
    )
    return Quote(rate, date.date(), GNUCASH_PRICE)
