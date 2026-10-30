import datetime
import decimal
import pathlib
import zoneinfo

import httpx
import pytest

from gnucash_quick_expense import rates

FIXTURES = pathlib.Path(__file__).with_name("fixtures")
PAGE = (FIXTURES / "murc-2026-10-30.html").read_bytes()
TOKYO = zoneinfo.ZoneInfo("Asia/Tokyo")
NO_RATES = httpx.Response(
    302,
    headers={
        "Location": "https://www.murc-kawasesouba.jp/fx/past_3month.php?caution=1"
    },
)


def test_parse_page_reads_ttm_per_unit():
    table = rates.parse_page(PAGE.decode("cp932"))
    assert table["USD"] == decimal.Decimal("157.54")
    assert table["EUR"] > 0
    assert "TWD" not in table
    assert "MOP" not in table


def test_parse_page_divides_hundred_unit_quotes():
    table = rates.parse_page(PAGE.decode("cp932"))
    assert table["KRW"] == decimal.Decimal("0.1177")
    assert table["IDR"] == decimal.Decimal("0.0088")


def test_parse_page_returns_empty_for_unexpected_html():
    assert rates.parse_page("<html><body>maintenance</body></html>") == {}


def test_parse_page_skips_rows_without_a_numeric_ttm():
    html = (
        '<table class="data-table5"><tr><th>Currency</th></tr>'
        "<td>X</td><td>x</td><td>XXX</td><td>1.00</td><td>-</td><td>-</td></tr>"
        "<td>Y</td><td>y</td><td>YYY</td><td>2.00</td><td>1.00</td><td>1.50</td></tr>"
        "</table>"
    )
    assert rates.parse_page(html) == {"YYY": decimal.Decimal("1.50")}


class _Site:
    """A fake MUFG site that serves the fixture for some dates."""

    def __init__(self, pages=None, error=None):
        self.pages = pages or {}
        self.error = error
        self.requests = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        params = request.url.params
        day = datetime.date(int(params["y"]), int(params["m"]), int(params["d"]))
        response = self.pages.get(day)
        if response is None:
            return NO_RATES
        return response


def _client(site: _Site, **kwargs) -> rates.MurcClient:
    return rates.MurcClient(
        httpx.AsyncClient(transport=httpx.MockTransport(site)), **kwargs
    )


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_ttm_walks_back_to_the_last_business_day():
    site = _Site({datetime.date(2026, 10, 30): httpx.Response(200, content=PAGE)})
    quote = await _client(site).ttm("USD", datetime.date(2026, 10, 31))
    assert quote == rates.Quote(
        decimal.Decimal("157.54"), datetime.date(2026, 10, 30), "MUFG TTM"
    )
    assert [r.url.params["d"] for r in site.requests] == ["31", "30"]
    assert site.requests[0].url.params["m"] == "10"


@pytest.mark.anyio
async def test_ttm_gives_up_after_max_days_back():
    site = _Site()
    assert (
        await _client(site, max_days_back=3).ttm("USD", datetime.date(2026, 10, 31))
        is None
    )
    assert len(site.requests) == 4


@pytest.mark.anyio
async def test_ttm_returns_none_for_unpublished_currency():
    site = _Site({datetime.date(2026, 10, 30): httpx.Response(200, content=PAGE)})
    assert await _client(site).ttm("TWD", datetime.date(2026, 10, 30)) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "site",
    [
        _Site(error=httpx.ConnectTimeout("timed out")),
        _Site({datetime.date(2026, 10, 30): httpx.Response(500)}),
        _Site({datetime.date(2026, 10, 30): httpx.Response(200, content=b"<html>")}),
    ],
    ids=["timeout", "http-500", "unexpected-html"],
)
async def test_ttm_returns_none_when_the_site_fails(site):
    assert (
        await _client(site, max_days_back=0).ttm("USD", datetime.date(2026, 10, 30))
        is None
    )


@pytest.mark.anyio
async def test_ttm_caches_past_days():
    site = _Site({datetime.date(2026, 10, 30): httpx.Response(200, content=PAGE)})
    client = _client(site)
    await client.ttm("USD", datetime.date(2026, 10, 30))
    await client.ttm("EUR", datetime.date(2026, 10, 30))
    assert len(site.requests) == 1


@pytest.mark.anyio
async def test_ttm_does_not_cache_today_without_rates():
    today = datetime.datetime.now(TOKYO).date()
    site = _Site()
    client = _client(site, max_days_back=0)
    assert await client.ttm("USD", today) is None
    site.pages[today] = httpx.Response(200, content=PAGE)
    quote = await client.ttm("USD", today)
    assert quote is not None
    assert quote.rate == decimal.Decimal("157.54")
    assert len(site.requests) == 2


@pytest.mark.anyio
async def test_ttm_does_not_cache_failures():
    site = _Site({datetime.date(2026, 10, 30): httpx.Response(500)})
    client = _client(site, max_days_back=0)
    assert await client.ttm("USD", datetime.date(2026, 10, 30)) is None
    site.pages[datetime.date(2026, 10, 30)] = httpx.Response(200, content=PAGE)
    assert await client.ttm("USD", datetime.date(2026, 10, 30)) is not None
