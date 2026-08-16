"""Tests for anti-bot detection logic."""

import unittest

from stealth_fetch.detection import detect_protection, is_blocked


class TestDetection(unittest.TestCase):
    def test_cloudflare_challenge(self):
        html = '<html><title>Just a moment...</title></html>'
        assert detect_protection(503, html) == "cloudflare"
        assert is_blocked(503, html)

    def test_cloudflare_attention_required(self):
        html = '<html><title>Attention Required! | Cloudflare</title></html>'
        assert detect_protection(403, html) == "cloudflare"

    def test_cloudflare_chl_marker(self):
        html = '<html><script src="/__cf_chl/scripts"></script></html>'
        assert detect_protection(200, html) == "cloudflare"

    def test_datadome(self):
        html = '<html><script src="https://dd.datadome.co/js/"></script></html>'
        assert detect_protection(403, html) == "datadome"

    def test_datadome_in_headers(self):
        assert detect_protection(403, "", {"set-cookie": "datadome=abc"}) == "datadome"

    def test_akamai(self):
        html = '<html><script src="/akam/13/abc"></script></html>'
        assert detect_protection(403, html) == "akamai"

    def test_captcha(self):
        html = '<html><div class="g-recaptcha"></div></html>'
        assert detect_protection(200, html) == "captcha"

    def test_empty_403(self):
        assert detect_protection(403, "") == "empty-block"
        assert detect_protection(403, "  \n  ") == "empty-block"

    def test_generic_403(self):
        html = '<html><body>Access Denied</body></html>'
        assert detect_protection(403, html) == "generic-block"

    def test_normal_page(self):
        html = '<html><body><h1>Hello</h1></body></html>'
        assert detect_protection(200, html) is None
        assert not is_blocked(200, html)

    def test_normal_404(self):
        html = '<html><body>Not Found</body></html>'
        assert detect_protection(404, html) is None


class TestAkamaiInterstitial(unittest.TestCase):
    """Régression : l'interstitiel Akamai est servi en 200 avec un corps long.

    L'heuristique « 200 + page longue = vrai contenu » le blanchissait, donc la
    cascade s'arrêtait au premier moteur en croyant tenir la page — alors qu'elle
    tenait la page de vérification. Constaté sur intramuros.org le 2026-08-16.
    """

    INTERSTITIAL = "<html><body><script>bm-verify</script>" + "x" * 9000 + "</body></html>"

    def test_detected_as_interstitial(self):
        self.assertEqual(detect_protection(200, self.INTERSTITIAL), "interstitial")

    def test_long_200_interstitial_is_still_blocked(self):
        self.assertTrue(is_blocked(200, self.INTERSTITIAL))

    def test_legitimate_akamai_page_not_blocked(self):
        """Un cookie _abck sur une vraie page ne doit PAS déclencher d'escalade."""
        html = "<html><body>_abck=xyz" + "contenu reel " * 900 + "</body></html>"
        self.assertFalse(is_blocked(200, html))


if __name__ == "__main__":
    unittest.main()
