import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import action_approval_service as approvals


class ActionApprovalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_patch = patch.object(
            approvals,
            "AUDIT_FILE",
            Path(self.temp_dir.name) / "action_audit.json",
        )
        self.audit_patch.start()
        with approvals._LOCK:
            approvals._pending_actions.clear()
        self.client = TestClient(app)

    def tearDown(self):
        with approvals._LOCK:
            approvals._pending_actions.clear()
        self.audit_patch.stop()
        self.temp_dir.cleanup()

    def test_api_approves_and_denies_one_time_action_ids(self):
        approved = approvals.get_approval_event(
            approvals.request_approval("task_clear", {"task": ""})
        )
        denied = approvals.get_approval_event(
            approvals.request_approval("task_clear", {"task": ""})
        )
        self.assertIsNotNone(approved)
        self.assertIsNotNone(denied)
        assert approved is not None
        assert denied is not None
        with patch(
            "app.services.task_service.manage_tasks",
            return_value="All tasks cleared.",
        ) as manage_tasks:
            approve_response = self.client.post(f"/actions/{approved['id']}/approve")
            replay_response = self.client.post(f"/actions/{approved['id']}/approve")
            deny_response = self.client.post(f"/actions/{denied['id']}/deny")

        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.json()["status"], "executed")
        self.assertEqual(replay_response.status_code, 404)
        self.assertEqual(deny_response.status_code, 200)
        self.assertEqual(deny_response.json()["status"], "denied")
        manage_tasks.assert_called_once_with("clear", "")

    def test_foreign_origins_cannot_resolve_approvals_or_read_audit(self):
        request = approvals.get_approval_event(
            approvals.request_approval("task_clear", {"task": ""})
        )
        assert request is not None
        headers = {"Origin": "https://untrusted.example"}

        approve_response = self.client.post(
            f"/actions/{request['id']}/approve",
            headers=headers,
        )
        audit_response = self.client.get("/actions/audit", headers=headers)

        self.assertEqual(approve_response.status_code, 403)
        self.assertEqual(audit_response.status_code, 403)

    def test_audit_endpoint_returns_bounded_events(self):
        approvals.request_approval("task_clear", {"task": ""})

        response = self.client.get("/actions/audit?limit=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["events"]), 1)
        self.assertEqual(response.json()["events"][0]["event"], "approval_requested")
        self.assertEqual(self.client.get("/actions/audit?limit=501").status_code, 422)

    def test_pending_endpoint_restores_the_confirmation_details(self):
        approval = approvals.get_approval_event(
            approvals.request_approval(
                "task_add",
                {"task": "Review changes"},
                "Task: Review changes",
            )
        )
        assert approval is not None

        response = self.client.get("/actions/pending")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["approvals"][0]["id"], approval["id"])
        self.assertEqual(
            response.json()["approvals"][0]["details"],
            "Task: Review changes",
        )


if __name__ == "__main__":
    unittest.main()
