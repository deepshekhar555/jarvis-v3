import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.services import action_approval_service as approvals


class ActionApprovalServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_file = Path(self.temp_dir.name) / "action_audit.json"
        self.task_file = Path(self.temp_dir.name) / "tasks.json"
        self.audit_patch = patch.object(approvals, "AUDIT_FILE", self.audit_file)
        self.audit_patch.start()
        with approvals._LOCK:
            approvals._pending_actions.clear()
        from app.services import task_service

        self.task_patch = patch.object(task_service, "TASK_FILE", self.task_file)
        self.task_patch.start()

    def tearDown(self):
        self.task_patch.stop()
        self.audit_patch.stop()
        with approvals._LOCK:
            approvals._pending_actions.clear()
        self.temp_dir.cleanup()

    def test_action_is_queued_until_approved_and_cannot_be_replayed(self):
        result = approvals.request_approval(
            "task_add",
            {"task": "Write tests"},
            "Task: Write tests",
        )
        request = approvals.get_approval_event(result)
        self.assertIsNotNone(request)
        assert request is not None
        self.assertFalse(self.task_file.exists())
        self.assertEqual(request["details"], "Task: Write tests")

        outcome = approvals.resolve_approval(request["id"], approve=True)

        self.assertEqual(outcome, {"status": "executed", "result": "Added task: 'Write tests'"})
        self.assertEqual(json.loads(self.task_file.read_text()), ["Write tests"])
        with self.assertRaises(approvals.ApprovalNotFoundError):
            approvals.resolve_approval(request["id"], approve=True)

        events = approvals.get_audit_events()
        self.assertEqual(
            [event["event"] for event in reversed(events)],
            ["approval_requested", "approved", "executed"],
        )
        self.assertNotIn("Write tests", self.audit_file.read_text(encoding="utf-8"))

    def test_denial_discards_action_without_side_effect(self):
        request = approvals.get_approval_event(
            approvals.request_approval("task_clear", {"task": ""})
        )
        assert request is not None

        outcome = approvals.resolve_approval(request["id"], approve=False)

        self.assertEqual(outcome["status"], "denied")
        self.assertFalse(self.task_file.exists())
        self.assertEqual(approvals.get_audit_events()[0]["event"], "denied")

    def test_expired_approval_cannot_execute(self):
        current_time = [datetime(2026, 11, 7, tzinfo=timezone.utc)]
        with patch.object(approvals, "_utc_now", side_effect=lambda: current_time[0]):
            request = approvals.get_approval_event(
                approvals.request_approval("task_add", {"task": "Expired task"})
            )
            assert request is not None
            current_time[0] += timedelta(seconds=approvals.APPROVAL_TTL_SECONDS + 1)

            with self.assertRaises(approvals.ApprovalExpiredError):
                approvals.resolve_approval(request["id"], approve=True)

        self.assertFalse(self.task_file.exists())
        self.assertEqual(approvals.get_audit_events()[0]["event"], "expired")

    def test_unknown_action_types_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "cannot be approved"):
            approvals.request_approval("arbitrary_command", {})

    def test_image_generation_is_deferred_until_approved(self):
        with patch(
            "app.services.image_generation_service.generate_image_asset",
            return_value="/static/generated_images/approved.png",
        ) as generate:
            request = approvals.get_approval_event(
                approvals.request_approval(
                    "image_generate",
                    {"prompt": "A lighthouse"},
                    "Prompt: A lighthouse",
                )
            )
            assert request is not None
            generate.assert_not_called()

            outcome = approvals.resolve_approval(request["id"], approve=True)

        self.assertEqual(outcome["image"], "/static/generated_images/approved.png")
        generate.assert_called_once_with("A lighthouse")

    def test_audit_limit_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "Limit must be"):
            approvals.get_audit_events(0)


if __name__ == "__main__":
    unittest.main()
