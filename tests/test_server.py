import json
import unittest
from unittest.mock import patch

import httpx

import server


class _AsyncClientStub:
    def __init__(self, response=None, post_error=None):
        self._response = response
        self._post_error = post_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        if self._post_error is not None:
            raise self._post_error
        return self._response


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_post_raises_upstream_api_error_for_http_status_failures(self):
        request = httpx.Request("POST", "https://example.com/news-search")
        response = httpx.Response(503, request=request, text="maintenance")
        http_error = httpx.HTTPStatusError("boom", request=request, response=response)

        with patch("server._get_apikey", return_value="test-key"), patch(
            "server.httpx.AsyncClient", return_value=_AsyncClientStub(post_error=http_error)
        ):
            with self.assertRaises(server.UpstreamAPIError) as ctx:
                await server._post("/news-search", {"query": "mx"})

        details = ctx.exception.details
        self.assertEqual(details["response"]["error_type"], "http_status_error")
        self.assertEqual(details["response"]["status_code"], 503)
        self.assertEqual(details["request"], {"query": "mx"})
        self.assertIn("maintenance", details["response"]["response_text"])
        self.assertEqual(json.loads(str(ctx.exception)), details)

    async def test_summary_marks_positions_overview_unavailable_when_positions_fail(self):
        balance_result = {
            "success_hint": True,
            "error_hint": None,
            "response": {"data": {"totalAssets": 123000}},
        }
        positions_result = {
            "success_hint": False,
            "error_hint": "positions temporarily unavailable",
            "response": {"status": 404, "message": "not bound"},
        }

        async def fake_post(path, payload=None):
            if path == "/mockTrading/balance":
                return balance_result
            if path == "/mockTrading/positions":
                return positions_result
            raise AssertionError(path)

        with patch("server._post", side_effect=fake_post):
            result = await server.mx_stock_simulator_summary()

        self.assertTrue(result["balance_status"])
        self.assertFalse(result["positions_status"])
        self.assertEqual(result["error_hint"], "positions temporarily unavailable")
        self.assertEqual(result["balance_money_fields"][0]["value_yuan"], 123.0)
        self.assertEqual(
            result["positions_overview"],
            {
                "available": False,
                "position_count": None,
                "total_market_value_li": None,
                "total_market_value_yuan": None,
                "total_profit_li": None,
                "total_profit_yuan": None,
                "top_positions": None,
                "error_hint": "positions temporarily unavailable",
            },
        )


if __name__ == "__main__":
    unittest.main()
