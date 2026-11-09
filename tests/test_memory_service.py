import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.memory_service import get_memory_context, manage_memory


class MemoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory_file = Path(self.temp_dir.name) / "memory.json"
        self.memory_patch = patch(
            "app.services.memory_service.MEMORY_FILE",
            self.memory_file,
        )
        self.memory_patch.start()

    def tearDown(self):
        self.memory_patch.stop()
        self.temp_dir.cleanup()

    def test_remember_list_and_forget_are_persistent(self):
        self.assertEqual(
            manage_memory("remember", "I prefer concise answers."),
            "Saved that note locally.",
        )
        self.assertEqual(json.loads(self.memory_file.read_text())[0]["text"],
                         "I prefer concise answers.")
        self.assertIn("I prefer concise answers.", manage_memory("list"))
        self.assertEqual(
            manage_memory("forget", "I prefer concise answers."),
            "Removed the matching note.",
        )
        self.assertEqual(manage_memory("list"), "There are no saved notes.")

    def test_rejects_credentials_and_oversized_notes(self):
        for note in ("my API key is abc123", "password: secret", "x" * 501):
            with self.subTest(note=note[:24]):
                with self.assertRaises(ValueError):
                    manage_memory("remember", note)
        self.assertFalse(self.memory_file.exists())

    def test_forget_requires_an_exact_match(self):
        manage_memory("remember", "I like tea.")

        result = manage_memory("forget", "I like tea")

        self.assertEqual(result, "I couldn't find an exact matching saved note.")
        self.assertIn("I like tea.", manage_memory("list"))

    def test_context_is_bounded_and_empty_when_no_notes_exist(self):
        self.assertEqual(get_memory_context(), "")
        manage_memory("remember", "I prefer concise answers.")

        self.assertIn("User-saved notes", get_memory_context())
        self.assertIn("I prefer concise answers.", get_memory_context())


if __name__ == "__main__":
    unittest.main()
