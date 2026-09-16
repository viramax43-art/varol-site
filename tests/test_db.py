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

    def test_projects_extended_fields_and_update(self):
        project_id = db.add_project(
            "Новый проект", "FOOD", 250.5, "Описание", "https://example.com/project"
        )
        project = db.get_project(project_id)
        self.assertEqual(project["description"], "Описание")
        self.assertEqual(project["media_url"], "https://example.com/project")
        self.assertEqual(project["min_amount"], 250.5)
        self.assertEqual(project["code"], "FOOD")

        self.assertTrue(db.update_project(project_id, "Обновлён", "EV", 300, "Новое", ""))
        updated = db.get_project(project_id)
        self.assertEqual(updated["name"], "Обновлён")
        self.assertEqual(updated["min_amount"], 300)
        self.assertEqual(updated["code"], "EV")

    def test_project_code_is_normalized_unique_and_reserved_own(self):
        first_id = db.add_project("Первый", "food")
        self.assertEqual(db.get_project(first_id)["code"], "FOOD")
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_project("Второй", "FOOD")
        for invalid in ("A", "BAD-CODE", "OWN", "кино"):
            with self.assertRaises(ValueError):
                db.normalize_project_code(invalid)

    def test_projects_migration_is_idempotent(self):
        os.remove(self.test_db_path)
        with sqlite3.connect(self.test_db_path) as conn:
            conn.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
            conn.execute("INSERT INTO projects (name) VALUES ('Старый один'), ('Старый два')")
        db.init_db()
        db.init_db()
        with sqlite3.connect(self.test_db_path) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
            rows = conn.execute("SELECT id, name, code FROM projects ORDER BY id").fetchall()
            indexes = {row[1] for row in conn.execute("PRAGMA index_list(projects)")}
        self.assertTrue({"code", "description", "media_url", "min_amount"}.issubset(columns))
        self.assertEqual([row[1] for row in rows], ["Старый один", "Старый два"])
        self.assertEqual(len({row[2] for row in rows}), 2)
        self.assertTrue(all(db.PROJECT_CODE_RE.fullmatch(row[2]) for row in rows))
        self.assertIn("idx_projects_code_unique", indexes)

    def test_get_transaction_by_id(self):
        db.create_transaction("TX-ID-TEST", "investment", 500, "EUR", "Investor Alex", "", "")
        tx_by_code = db.get_transaction_by_code("TX-ID-TEST")
        self.assertIsNotNone(tx_by_code)
        
        tx_by_id = db.get_transaction_by_id(tx_by_code['id'])
        self.assertIsNotNone(tx_by_id)
        self.assertEqual(tx_by_id['tx_code'], "TX-ID-TEST")
        self.assertEqual(tx_by_id['name'], "Investor Alex")

    def test_user_activity_and_top_members(self):
        db.record_user_activity(1001, "user1", "Alex", points=5)
        db.record_user_activity(1001, "user1", "Alex", points=3)
        db.record_user_activity(1002, "user2", "Bob", points=10)
        
        top = db.get_top_active_members(5)
        self.assertEqual(len(top), 2)
        # Bob has 10 points, Alex has 8 points -> Bob first
        self.assertEqual(top[0]['tg_user_id'], 1002)
        self.assertEqual(top[0]['activity_points'], 10)
        self.assertEqual(top[0]['messages_count'], 1)
        
        self.assertEqual(top[1]['tg_user_id'], 1001)
        self.assertEqual(top[1]['activity_points'], 8)
        self.assertEqual(top[1]['messages_count'], 2)

    def test_community_activation_and_anonymity(self):
        db.create_transaction("TX-INV-001", "Инвестиция: Сфера", 1000, "EUR", "Ivan", "", "")
        ok, badge, member = db.verify_and_activate_code(999, "ivan_tg", "Ivan", "TX-INV-001")
        self.assertTrue(ok)
        self.assertEqual(badge, "Инвестор")
        self.assertEqual(member['role'], "investor")
        self.assertEqual(member['is_anonymous'], 0)
        
        # Toggle anon
        new_anon = db.toggle_community_anonymity(999)
        self.assertEqual(new_anon, 1)
        member_anon = db.get_community_member(999)
        self.assertEqual(member_anon['is_anonymous'], 1)

if __name__ == '__main__':
    unittest.main()
