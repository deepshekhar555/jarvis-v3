import unittest
from unittest.mock import patch

from app.services.tools_service import (
    generate_image,
    manage_memory,
    manage_project_plans,
    manage_tasks,
    system_control,
)


class ApprovedToolRequestTests(unittest.TestCase):
    @patch(
        "app.services.action_approval_service.request_approval",
        return_value="approval marker",
    )
    def test_task_mutations_are_queued_but_listing_is_read_only(self, request_approval):
        queued = manage_tasks.invoke({"action": "add", "task": "Review changes"})
        self.assertEqual(queued, "approval marker")
        request_approval.assert_called_once_with(
            "task_add",
            {"task": "Review changes"},
            "Task: Review changes",
        )

        request_approval.reset_mock()
        with patch("app.services.task_service.manage_tasks", return_value="No tasks currently on the board."):
            result = manage_tasks.invoke({"action": "list"})
        self.assertIn("No tasks", result)
        request_approval.assert_not_called()

    @patch(
        "app.services.action_approval_service.request_approval",
        return_value="approval marker",
    )
    def test_memory_and_project_writes_request_approval(self, request_approval):
        self.assertEqual(
            manage_memory.invoke(
                {"action": "remember", "information": "I prefer short answers."}
            ),
            "approval marker",
        )
        self.assertEqual(
            request_approval.call_args.args[0],
            "memory_remember",
        )

        request_approval.reset_mock()
        self.assertEqual(
            manage_project_plans.invoke(
                {
                    "action": "save",
                    "project_name": "Study Assistant",
                    "plan": "Architecture and milestones.",
                }
            ),
            "approval marker",
        )
        self.assertEqual(request_approval.call_args.args[0], "project_save")

    @patch(
        "app.services.action_approval_service.request_approval",
        return_value="approval marker",
    )
    def test_image_generation_and_system_setting_changes_require_approval(self, request_approval):
        self.assertEqual(
            generate_image.invoke({"prompt": "A calm mountain lake"}),
            "approval marker",
        )
        self.assertEqual(request_approval.call_args.args[0], "image_generate")

        request_approval.reset_mock()
        self.assertEqual(
            system_control.invoke({"action": "set_volume", "value": 35}),
            "approval marker",
        )
        self.assertEqual(request_approval.call_args.args[0], "system_set_volume")

    @patch(
        "app.services.action_approval_service.request_approval",
        return_value="approval marker",
    )
    def test_invalid_or_sensitive_mutations_are_not_queued(self, request_approval):
        memory_result = manage_memory.invoke(
            {"action": "remember", "information": "my API key is secret"}
        )
        setting_result = system_control.invoke({"action": "set_brightness", "value": 101})
        image_result = generate_image.invoke({"prompt": "  "})

        self.assertIn("Do not save", memory_result)
        self.assertIn("between 0 and 100", setting_result)
        self.assertIn("Provide a prompt", image_result)
        request_approval.assert_not_called()


if __name__ == "__main__":
    unittest.main()
