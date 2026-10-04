from __future__ import annotations

import unittest
import sqlite3

from huishi.admin_activity import merge_activity_rows, query_activity_page


class MergeActivityRowsTests(unittest.TestCase):
    def test_generation_and_charge_merge_into_one_event(self):
        records = [
            {
                "id": 10,
                "user_id": 2,
                "username": "mira",
                "prompt": "scene",
                "mode": "text",
                "resolution": "2K",
                "actual_size": "2560x1440",
                "model_source": "gpt-image-2",
                "created_at": "2026-07-12T10:00:00",
            }
        ]
        ledger = [
            {
                "id": 90,
                "user_id": 2,
                "username": "mira",
                "delta": -2,
                "reason": "generation",
                "record_id": 10,
                "created_at": "2026-07-12T10:00:01",
            }
        ]

        rows = merge_activity_rows(records, ledger)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "image_generation")
        self.assertEqual(rows[0]["points_delta"], -2)
        self.assertEqual(rows[0]["record_id"], 10)
        self.assertEqual(rows[0]["ledger_id"], 90)

    def test_generation_event_exposes_banana_display_name_separately_from_model_id(self):
        rows = merge_activity_rows(
            [
                {
                    "id": 12,
                    "user_id": 2,
                    "username": "mira",
                    "prompt": "scene",
                    "mode": "text",
                    "model_source": "gemini-3-pro-image",
                    "created_at": "2026-07-12T10:00:00",
                }
            ],
            [],
        )

        self.assertEqual(rows[0]["model_source"], "gemini-3-pro-image")
        self.assertEqual(rows[0]["model_label"], "Nano Banana Pro")

    def test_reward_without_record_remains_visible(self):
        rows = merge_activity_rows(
            [],
            [
                {
                    "id": 91,
                    "user_id": 2,
                    "username": "mira",
                    "delta": 100,
                    "reason": "invite_reward",
                    "record_id": None,
                    "created_at": "2026-07-12T11:00:00",
                }
            ],
        )

        self.assertEqual(rows[0]["event_type"], "invite_reward")
        self.assertIsNone(rows[0]["record_id"])

    def test_refund_is_not_duplicated_with_failed_record(self):
        records = [
            {
                "id": 11,
                "user_id": 2,
                "username": "mira",
                "prompt": "scene",
                "mode": "text",
                "resolution": "4K",
                "actual_size": "3840x2160",
                "model_source": "gpt-image-2",
                "status": "failed",
                "created_at": "2026-07-12T12:00:00",
            }
        ]
        ledger = [
            {
                "id": 92,
                "user_id": 2,
                "username": "mira",
                "delta": 6,
                "reason": "generation_refund",
                "record_id": 11,
                "created_at": "2026-07-12T12:00:03",
            }
        ]

        rows = merge_activity_rows(records, ledger)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "generation_refund")
        self.assertEqual(rows[0]["status"], "refunded")

    def test_unknown_ledger_reason_is_kept_as_other(self):
        rows = merge_activity_rows(
            [],
            [
                {
                    "id": 93,
                    "user_id": 2,
                    "username": "mira",
                    "delta": -3,
                    "reason": "legacy_custom_reason",
                    "record_id": None,
                    "created_at": "2026-07-12T13:00:00",
                }
            ],
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "other")
        self.assertEqual(rows[0]["reason"], "legacy_custom_reason")

    def test_admin_initial_ledger_is_a_named_credit_event(self):
        rows = merge_activity_rows(
            [],
            [
                {
                    "id": 95,
                    "user_id": 2,
                    "username": "mira",
                    "delta": 25,
                    "reason": "admin_initial",
                    "record_id": None,
                    "created_at": "2026-07-12T14:30:00+00:00",
                }
            ],
        )

        self.assertEqual(rows[0]["event_type"], "admin_initial")
        self.assertEqual(rows[0]["event_label"], "初始积分")
        self.assertEqual(rows[0]["status"], "credited")

    def test_linked_zero_delta_is_not_replaced_by_record_charge(self):
        rows = merge_activity_rows(
            [{"id": 12, "user_id": 2, "username": "mira", "prompt": "free", "points_charged": 9, "created_at": "2026-07-12T14:00:00"}],
            [{"id": 94, "user_id": 2, "username": "mira", "delta": 0, "reason": "generation", "record_id": 12, "created_at": "2026-07-12T14:00:01"}],
        )

        self.assertEqual(rows[0]["points_delta"], 0)


class QueryActivityPageTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL);
            CREATE TABLE records (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                prompt TEXT,
                mode TEXT,
                resolution TEXT,
                actual_size TEXT,
                model_source TEXT,
                points_charged INTEGER,
                asset_source TEXT,
                created_at TEXT
            );
            CREATE TABLE point_ledger (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                delta INTEGER,
                reason TEXT,
                record_id INTEGER,
                admin_note TEXT,
                created_at TEXT
            );
            """
        )
        self.db.executemany("INSERT INTO users (id, username) VALUES (?, ?)", [(2, "mira"), (3, "other")])
        self.db.executemany(
            """
            INSERT INTO records
            (id, user_id, prompt, mode, resolution, actual_size, model_source, points_charged, asset_source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (10, 2, "moon scene", "text", "2K", "2048x2048", "gpt-image-2", 2, "image", "2026-07-12T10:00:00+00:00"),
                (11, 3, "other scene", "image", "1K", "1024x1024", "gpt-image-2", 1, "image", "2026-07-12T10:30:00+00:00"),
            ],
        )
        self.db.executemany(
            """
            INSERT INTO point_ledger
            (id, user_id, delta, reason, record_id, admin_note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (90, 2, -2, "generation", 10, "", "2026-07-12T10:00:01+00:00"),
                (91, 2, 100, "invite_reward", None, "邀请奖励", "2026-07-12T11:00:00+00:00"),
                (92, 3, -1, "generation", 11, "", "2026-07-12T10:30:01+00:00"),
            ],
        )

    def tearDown(self):
        self.db.close()

    def test_filters_unified_events_by_user_event_mode_and_date(self):
        page = query_activity_page(
            db=self.db,
            search="moon",
            user="mira",
            event_type="image_generation",
            mode="text",
            from_date="2026-07-01",
            to_date="2026-07-31",
            page=1,
            per_page=20,
        )

        self.assertEqual(page.total, 1)
        self.assertEqual(page.rows[0]["record_id"], 10)
        self.assertEqual(page.rows[0]["ledger_id"], 90)

    def test_unified_total_and_pagination_include_standalone_ledger(self):
        page = query_activity_page(db=self.db, user_id=2, page=1, per_page=10)

        self.assertEqual(page.total, 2)
        self.assertEqual([row["event_type"] for row in page.rows], ["invite_reward", "image_generation"])


if __name__ == "__main__":
    unittest.main()
