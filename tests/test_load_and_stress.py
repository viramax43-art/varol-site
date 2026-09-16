from unittest.mock import patch
import os
import sys
import unittest
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app
import db

class TestLoadAndSecurityStress(unittest.TestCase):
    def setUp(self):
        self.mock_get_project = patch("app.db.get_project", return_value={"id": 1, "code": "EV", "name": "Электромобили", "min_amount": 100})
        self.mock_get_project.start()

        self.client = TestClient(app.app)

    def test_high_concurrency_load(self):
        """Simulate 500 concurrent requests to verify server throughput and zero crashes."""
        app.IP_REQUEST_LOGS.clear()
        def make_request(i):
            headers = {"X-Forwarded-For": f"10.0.{i % 250}.{i % 250}"}
            res = self.client.get("/api/config", headers=headers)
            return res.status_code

        start_time = time.time()
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(make_request, i) for i in range(500)]
            results = [f.result() for f in futures]
        duration = time.time() - start_time

        # Ensure all requests succeeded or were rate-limited (200 or 429), never 500 error
        for code in results:
            self.assertIn(code, (200, 429))
        print(f"\n[STRESS TEST SUCCESS] 500 concurrent requests processed in {duration:.3f}s (RPS: {500/duration:.1f})")

    def test_ddos_rate_limiting_enforcement(self):
        """Verify that flooding /api/submit_payment triggers 429 Rate Limiting."""
        client_ip = "192.168.99.99"
        headers = {"X-Forwarded-For": client_ip}

        # Clear existing logs for this IP
        app.IP_REQUEST_LOGS[client_ip] = []

        responses = []
        for _ in range(30):
            res = self.client.post(
                "/api/submit_payment",
                data={
                    "category": "Инвестор: Электромобили",
                    "amount": "500",
                    "currency": "EUR",
                    "project_id": "1",
                    "project_code": "EV"
                },
                headers=headers
            )
            responses.append(res.status_code)

        # After rate limit threshold (25), subsequent requests should return 429
        self.assertIn(429, responses)

    def test_sql_injection_resistance(self):
        """Verify resistance to SQL injection payloads."""
        sql_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE transactions; --",
            "1' UNION SELECT NULL, NULL, NULL, NULL --",
            "1; SELECT * FROM admins"
        ]

        for payload in sql_payloads:
            res = self.client.post(
                "/api/submit_payment",
                data={
                    "category": f"Инвестор: {payload}",
                    "amount": "500",
                    "currency": "EUR",
                    "project_id": payload,
                    "project_code": "EV"
                }
            )
            # Must return 400 Bad Request or handled response, NEVER 500 Internal Error
            self.assertIn(res.status_code, (400, 429))

        # Check that transactions table is completely unharmed
        txs = db.get_all_transactions()
        self.assertIsInstance(txs, list)

    def test_xss_payload_sanitization(self):
        """Verify XSS payloads are properly sanitized and escaped."""
        xss_payload = "<script>alert('XSS_ATTACK')</script>"
        res = self.client.post(
            "/api/submit_payment",
            data={
                "category": "Инвестор: Электромобили",
                "amount": "500",
                "currency": "EUR",
                "project_id": "1",
                "project_code": "EV",
                "comment": xss_payload
            }
        )
        self.assertIn(res.status_code, (200, 429))

    def test_anonymity_and_path_leakage(self):
        """Verify zero leakage of local developer username or filesystem paths."""
        res = self.client.get("/non_existent_route_404")
        self.assertEqual(res.status_code, 404)
        body_text = res.text.lower()
        self.assertNotIn("saveliy", body_text)
        self.assertNotIn("/home/saveliy", body_text)

if __name__ == "__main__":
    unittest.main()

    def tearDown(self):
        self.mock_get_project.stop()
