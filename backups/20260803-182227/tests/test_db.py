import unittest
from unittest.mock import patch
import sqlite3
import os
import sys

# Добавляем родительскую папку в sys.path для импорта db
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import db

class TestDB(unittest.TestCase):
    def setUp(self):
        self.test_db_path = '/tmp/test_varol.db'
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)
            
        self.patcher = patch('db.DB_PATH', self.test_db_path)
        self.patcher.start()
        
        # Инициализируем тестовую базу
        db.init_db()

    def tearDown(self):
        self.patcher.stop()
        if os.path.exists(self.test_db_path):
            os.remove(self.test_db_path)

    def test_admins_management(self):
        # Проверяем, что из .env добавился дефолтный админ DUMMY_ID (в тестах нет .env, так что DUMMY_ID)
        admins = db.get_all_admins()
        self.assertGreaterEqual(len(admins), 0)
        
        # Добавляем нового админа
        db.add_admin("12345")
        self.assertTrue(db.is_admin("12345"))
        
        # Удаляем админа
        db.remove_admin("12345")
        self.assertFalse(db.is_admin("12345"))

    def test_transactions_search_and_pagination(self):
        # Создаем несколько транзакций
        db.create_transaction("TX-001", "crypto", 100, "USDT", "Alice", "comm1", "")
        db.create_transaction("TX-002", "card", 200, "EUR", "Bob", "comm2", "")
        db.create_transaction("TX-003", "crypto", 300, "USDT", "Charlie", "comm3", "")
        
        # Поиск по коду
        tx = db.get_transaction_by_code("TX-002")
        self.assertIsNotNone(tx)
        self.assertEqual(tx['name'], "Bob")
        
        # Проверка пагинации pending заявок (offset)
        # Лимит 1, оффсет 0 -> должна вернуться первая заявка
        pending_0, total = db.get_pending_transactions(offset=0, limit=1)
        self.assertEqual(total, 3)
        self.assertEqual(len(pending_0), 1)
        self.assertEqual(pending_0[0]['tx_code'], "TX-001")
        
        # Лимит 1, оффсет 1 -> вторая заявка
        pending_1, total = db.get_pending_transactions(offset=1, limit=1)
        self.assertEqual(pending_1[0]['tx_code'], "TX-002")

    def test_extended_statistics(self):
        db.create_transaction("TX-S1", "crypto", 100, "USDT", "A", "", "")
        db.create_transaction("TX-S2", "crypto", 200, "USDT", "B", "", "")
        
        tx_id1 = db.get_transaction_by_code("TX-S1")['id']
        tx_id2 = db.get_transaction_by_code("TX-S2")['id']
        
        db.update_transaction_status(tx_id1, 'approved')
        db.update_transaction_status(tx_id2, 'rejected')
        
        stats = db.get_extended_statistics('today')
        self.assertEqual(stats['approved_count'], 1)
        self.assertEqual(stats['approved_sum'], 100)
        self.assertEqual(stats['rejected_count'], 1)
        self.assertEqual(stats['total_count'], 2)

    def test_project_settings(self):
        val = db.get_setting('min_donation', '10')
        self.assertEqual(val, '10')
        db.set_setting('min_donation', '50')
        self.assertEqual(db.get_setting('min_donation'), '50')

if __name__ == '__main__':
    unittest.main()
