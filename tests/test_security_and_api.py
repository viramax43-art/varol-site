import os
import sys
import unittest
import io
from unittest.mock import patch
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app
import db

class TestSecurityAndAPI(unittest.TestCase):
    def setUp(self):
        self.mock_get_project = patch("app.db.get_project", return_value={"id": 1, "code": "EV", "name": "Электромобили", "min_amount": 100})
        self.mock_get_project.start()

        app.IP_REQUEST_LOGS.clear()
        self.client = TestClient(app.app)

    def test_security_headers_present(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertEqual(response.headers.get("x-xss-protection"), "1; mode=block")

    def test_admin_auth_protection(self):
        # Request without header should be rejected (401)
        res1 = self.client.get("/api/admin/data")
        self.assertEqual(res1.status_code, 401)

        # Request with wrong password should be rejected (401)
        res2 = self.client.get("/api/admin/data", headers={"X-Admin-Pass": "wrong_password"})
        self.assertEqual(res2.status_code, 401)

        # Request with correct password should succeed (200)
        res3 = self.client.get("/api/admin/data", headers={"X-Admin-Pass": app.ADMIN_PASSWORD})
        self.assertEqual(res3.status_code, 200)

    def test_reject_executable_upload(self):
        # Fake PHP script disguised as receipt
        php_content = b"<?php echo 'hacked'; ?>"
        response = self.client.post(
            "/api/submit_payment",
            data={
                "category": "Инвестор: Электромобили",
                "amount": "500",
                "currency": "EUR",
                "project_id": "1",
                "project_code": "EV",
                "contact": "@testuser"
            },
            files={"receipt": ("hack.php", php_content, "application/x-php")}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file format", response.json().get("detail", ""))

    def test_valid_image_upload_generates_safe_path(self):
        # 1x1 GIF image bytes
        gif_bytes = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        response = self.client.post(
            "/api/submit_payment",
            data={
                "category": "Инвестор: Электромобили",
                "amount": "500",
                "currency": "EUR",
                "project_id": "1",
                "project_code": "EV",
                "contact": "@testinvestor"
            },
            files={"receipt": ("receipt.gif", gif_bytes, "image/gif")}
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data.get("status"), "success")
        self.assertTrue(res_data.get("tx_code", "").startswith("TX-EV-"))

if __name__ == "__main__":
    unittest.main()

    def tearDown(self):
        self.mock_get_project.stop()
