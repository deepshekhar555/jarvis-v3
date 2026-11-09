import unittest
from unittest.mock import patch

from skills.os_ops import launch_application


class LaunchApplicationTests(unittest.TestCase):
    @patch("skills.os_ops.subprocess.Popen")
    @patch("skills.os_ops.shutil.which", return_value=r"C:\Windows\System32\notepad.exe")
    def test_supported_alias_launches_without_a_shell(self, which, popen):
        result = launch_application("notepad")

        self.assertEqual(result, "Opening notepad.")
        which.assert_called_once_with("notepad.exe")
        popen.assert_called_once_with(
            [r"C:\Windows\System32\notepad.exe"],
            shell=False,
        )

    @patch("skills.os_ops.subprocess.Popen")
    @patch("skills.os_ops.shutil.which", return_value=None)
    def test_unknown_application_reports_that_it_was_not_found(self, which, popen):
        result = launch_application("an-app-that-is-not-installed")

        self.assertIn("Could not find", result)
        which.assert_called_once_with("an-app-that-is-not-installed")
        popen.assert_not_called()

    @patch("skills.os_ops.subprocess.Popen")
    @patch("skills.os_ops.shutil.which")
    def test_command_arguments_and_paths_are_rejected(self, which, popen):
        for app_name in ("notepad.exe & calc.exe", r"C:\Windows\notepad.exe"):
            with self.subTest(app_name=app_name):
                result = launch_application(app_name)
                self.assertIn("not a path or command", result)

        which.assert_not_called()
        popen.assert_not_called()

    @patch("skills.os_ops.subprocess.Popen", side_effect=OSError("permission denied"))
    @patch("skills.os_ops.shutil.which", return_value=r"C:\Tools\sample.exe")
    def test_launch_errors_are_returned(self, which, popen):
        result = launch_application("sample.exe")

        self.assertEqual(result, "Failed to open sample.exe: permission denied")


if __name__ == "__main__":
    unittest.main()
