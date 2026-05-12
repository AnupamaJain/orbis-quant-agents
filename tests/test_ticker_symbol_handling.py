import unittest

from cli.utils import normalize_ticker_symbol
from orbisquantagents.agents.utils.agent_utils import build_instrument_context


class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")
        self.assertEqual(normalize_ticker_symbol(" reliance.ns "), "RELIANCE.NS")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        context_ns = build_instrument_context("RELIANCE.NS")
        self.assertIn("RELIANCE.NS", context_ns)
        self.assertIn("exchange suffix", context)


if __name__ == "__main__":
    unittest.main()
