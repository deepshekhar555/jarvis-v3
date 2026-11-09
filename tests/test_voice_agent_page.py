import unittest

from fastapi.testclient import TestClient

from app.main import app


class VoiceAgentPageTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_voice_agent_page_and_assets_are_served(self):
        page = self.client.get("/voice-agent/")
        script = self.client.get("/voice-agent/voice-agent.js")
        style = self.client.get("/voice-agent/style.css")

        self.assertEqual(page.status_code, 200)
        self.assertIn("J.A.R.V.I.S Voice Agent", page.text)
        self.assertEqual(script.status_code, 200)
        self.assertIn("SpeechRecognition", script.text)
        self.assertEqual(style.status_code, 200)
