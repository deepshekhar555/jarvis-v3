import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.project_plan_service import manage_project_plans


class ProjectPlanServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.plans_dir = Path(self.temp_dir.name) / "project_plans"
        self.plans_patch = patch(
            "app.services.project_plan_service.PROJECT_PLANS_DIR",
            self.plans_dir,
        )
        self.plans_patch.start()

    def tearDown(self):
        self.plans_patch.stop()
        self.temp_dir.cleanup()

    def test_save_list_read_update_and_delete(self):
        self.assertEqual(
            manage_project_plans("save", "Jarvis Planner", "Architecture and milestones."),
            "Saved the project plan 'Jarvis Planner' locally.",
        )
        stored = json.loads((self.plans_dir / "jarvis-planner.json").read_text())
        self.assertEqual(stored["plan"], "Architecture and milestones.")
        self.assertIn("Jarvis Planner", manage_project_plans("list"))
        self.assertIn(
            "Architecture and milestones.",
            manage_project_plans("read", "jarvis planner"),
        )
        self.assertEqual(
            manage_project_plans("update", "Jarvis Planner", "Revised architecture."),
            "Updated the project plan 'Jarvis Planner'.",
        )
        self.assertIn("Revised architecture.", manage_project_plans("read", "Jarvis Planner"))
        self.assertEqual(
            manage_project_plans("delete", "Jarvis Planner"),
            "Deleted the project plan 'Jarvis Planner'.",
        )
        self.assertEqual(manage_project_plans("list"), "There are no saved project plans.")

    def test_save_does_not_overwrite_existing_or_colliding_names(self):
        manage_project_plans("save", "AI Plan", "First plan.")

        duplicate = manage_project_plans("save", "ai plan", "Replacement.")
        collision = manage_project_plans("save", "AI-Plan", "Different plan.")

        self.assertIn("already exists", duplicate)
        self.assertIn("conflicts", collision)
        self.assertIn("First plan.", manage_project_plans("read", "AI Plan"))

    def test_rejects_unsafe_names_and_missing_or_oversized_content(self):
        invalid_names = ("../outside", r"folder\\plan", "CON")
        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    manage_project_plans("save", name, "A plan.")

        with self.assertRaisesRegex(ValueError, "Provide the project plan"):
            manage_project_plans("save", "Empty plan", "  ")
        with self.assertRaisesRegex(ValueError, "30,000 characters or fewer"):
            manage_project_plans("save", "Large plan", "x" * 30_001)
        self.assertFalse(self.plans_dir.exists())

    def test_save_and_update_require_existing_plan_as_appropriate(self):
        self.assertIn(
            "couldn't find",
            manage_project_plans("update", "Missing plan", "A plan."),
        )
        self.assertIn("Saved", manage_project_plans("save", "Saved", "A plan."))
        self.assertIn("already exists", manage_project_plans("save", "Saved", "A plan."))
        self.assertIn(
            "couldn't find",
            manage_project_plans("read", "Missing plan"),
        )

    def test_invalid_actions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Action must be"):
            manage_project_plans("run", "Project", "Plan.")


if __name__ == "__main__":
    unittest.main()
