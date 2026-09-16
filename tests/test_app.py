import os
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app


class TestPaymentValidation(unittest.TestCase):
    def test_individual_project_minimum_and_matching_code(self):
        project = {"id": 7, "name": "Energy", "code": "EV", "min_amount": 250}
        with patch("app.db.get_project", return_value=project):
            self.assertEqual(
                app.validate_payment_target("Инвестор: Energy", "7", "ev", Decimal("250")),
                "EV",
            )
            with self.assertRaises(HTTPException) as below_min:
                app.validate_payment_target("Инвестор: Energy", "7", "EV", Decimal("249.99"))
            self.assertEqual(below_min.exception.status_code, 400)
            with self.assertRaises(HTTPException):
                app.validate_payment_target("Инвестор: Energy", "7", "FOOD", Decimal("300"))

    def test_own_project_code_and_global_minimum(self):
        with patch("app.db.get_setting", return_value="100"):
            self.assertEqual(
                app.validate_payment_target("Инвестор: Предложить свой", "-1", "OWN", Decimal("100")),
                "OWN",
            )
            with self.assertRaises(HTTPException):
                app.validate_payment_target("Инвестор: Предложить свой", "-1", "EV", Decimal("100"))

    def test_tx_code_only_changes_format_for_investment(self):
        donation = app.generate_tx_code(Decimal("12.34"))
        investment = app.generate_tx_code(Decimal("12.34"), "EV")
        self.assertRegex(donation, r"^TX-\d{12}-1234-[A-Z0-9]{4}$")
        self.assertRegex(investment, r"^TX-EV-\d{12}-1234-[A-Z0-9]{4}$")

    def test_amount_helper_rejects_non_finite_and_minimum(self):
        for invalid in ("0", "-1", "nan", "inf", "nope"):
            with self.assertRaises(HTTPException):
                app.parse_positive_amount(invalid)
        with self.assertRaises(HTTPException):
            app.validate_min_amount(Decimal("4.99"), "5")


if __name__ == "__main__":
    unittest.main()
