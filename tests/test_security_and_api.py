import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tests.bootstrap_env  # noqa: F401, E402
import app
import admin_auth

TEST_PASSWORD = "TestAdminPassword2024!Secure"


class TestSecurityAndAPI(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch(
                "app.db.get_project",
                return_value={"id": 1, "code": "EV", "name": "Электромобили", "min_amount": 100},
            ),
            patch("app.db.get_setting", side_effect=lambda key, default="": default),
            patch("app.db.get_all_banks", return_value=[]),
            patch("app.db.get_all_projects", return_value=[]),
            patch("app.db.get_active_projects", return_value=[]),
            patch("app.db.create_transaction", return_value=1),
            patch("app.db.update_transaction_status"),
        ]
        for item in self.patches:
            item.start()

        app.IP_REQUEST_LOGS.clear()
        self.client = TestClient(app.app)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_security_headers_present(self):
        response = self.client.get("/api/config")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertEqual(response.headers.get("x-xss-protection"), "1; mode=block")

    def test_admin_auth_protection(self):
        res1 = self.client.get(f"{app.ADMIN_API_PREFIX}/data")
        self.assertEqual(res1.status_code, 401)

        with patch("admin_auth.db.get_admin_password_hash", return_value="stored_hash"), patch(
            "admin_auth.verify_password", return_value=True
        ), patch("admin_auth.db.create_admin_session"):
            login_res = self.client.post(
                f"{app.ADMIN_API_PREFIX}/login",
                json={"password": TEST_PASSWORD},
            )
            self.assertEqual(login_res.status_code, 200)
            cookie = login_res.cookies.get(admin_auth.SESSION_COOKIE)
            self.assertTrue(cookie)

        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch("admin_auth.db.get_admin_session", return_value={"expires_at": expires_at}):
            res2 = self.client.get(
                f"{app.ADMIN_API_PREFIX}/data",
                cookies={admin_auth.SESSION_COOKIE: cookie},
            )
            self.assertEqual(res2.status_code, 200)

    def test_legacy_admin_routes_removed(self):
        self.assertEqual(self.client.get("/admin").status_code, 404)
        self.assertEqual(self.client.get("/api/admin/data").status_code, 404)
        self.assertEqual(self.client.post("/api/admin/login", json={"password": "x"}).status_code, 404)

    def test_password_strength_rules(self):
        with self.assertRaises(RuntimeError):
            admin_auth.validate_password_strength("short")
        with self.assertRaises(RuntimeError):
            admin_auth.validate_password_strength("  longpassword1234567890")
        admin_auth.validate_password_strength(TEST_PASSWORD)

    def test_reject_executable_upload(self):
        php_content = b"<?php echo 'hacked'; ?>"
        response = self.client.post(
            "/api/submit_payment",
            data={
                "category": "Инвестор: Электромобили",
                "amount": "500",
                "currency": "EUR",
                "project_id": "1",
                "project_code": "EV",
                "contact": "@testuser",
            },
            files={"receipt": ("hack.php", php_content, "application/x-php")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid file format", response.json().get("detail", ""))

    def test_valid_image_upload_generates_safe_path(self):
        gif_bytes = (
            b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,"
            b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        )
        response = self.client.post(
            "/api/submit_payment",
            data={
                "category": "Инвестор: Электромобили",
                "amount": "500",
                "currency": "EUR",
                "project_id": "1",
                "project_code": "EV",
                "contact": "@testinvestor",
            },
            files={"receipt": ("receipt.gif", gif_bytes, "image/gif")},
        )
        self.assertEqual(response.status_code, 200)
        res_data = response.json()
        self.assertEqual(res_data.get("status"), "success")
        self.assertTrue(res_data.get("tx_code", "").startswith("TX-EV-"))


if __name__ == "__main__":
    unittest.main()
