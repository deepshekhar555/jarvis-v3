import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient

from app.main import BASE_DIR, app
from app.services.vision_service import (
    MAX_IMAGE_BYTES,
    VisionProviderError,
    analyze_image,
    detect_image_media_type,
)


class ImageMediaTypeTests(unittest.TestCase):
    def test_detects_supported_image_signatures(self):
        self.assertEqual(detect_image_media_type(b"\x89PNG\r\n\x1a\ncontent"), "image/png")
        self.assertEqual(detect_image_media_type(b"\xff\xd8\xffcontent"), "image/jpeg")
        self.assertEqual(
            detect_image_media_type(b"RIFF\x04\x00\x00\x00WEBPcontent"),
            "image/webp",
        )

    def test_rejects_empty_oversized_and_unknown_files(self):
        invalid_images = (
            (b"", "empty"),
            (b"\x89PNG\r\n\x1a\n" + b"x" * MAX_IMAGE_BYTES, "8 MB or smaller"),
            (b"not an image", "valid PNG, JPEG, or WebP"),
        )
        for image, expected_error in invalid_images:
            with self.subTest(expected_error=expected_error):
                with self.assertRaisesRegex(ValueError, expected_error):
                    detect_image_media_type(image)


class AnalyzeImageTests(unittest.IsolatedAsyncioTestCase):
    @patch("config.OPENAI_API_KEY", "")
    async def test_missing_api_key_is_reported_without_request(self):
        with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY is not configured"):
            await analyze_image(b"\x89PNG\r\n\x1a\nimage", "image/png")

    @patch("config.OPENAI_MODEL", "vision-test-model")
    @patch("config.OPENAI_API_KEY", "test-key")
    async def test_sends_image_to_configured_model_and_returns_description(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="A test image description.")
                )
            ]
        )
        create = AsyncMock(return_value=response)
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            close=AsyncMock(),
        )
        openai_module = ModuleType("openai")
        openai_module.APIError = type("APIError", (Exception,), {})
        openai_module.AsyncOpenAI = Mock(return_value=client)

        with patch.dict("sys.modules", {"openai": openai_module}):
            result = await analyze_image(b"\x89PNG\r\n\x1a\nimage", "image/png")

        self.assertEqual(result, "A test image description.")
        openai_module.AsyncOpenAI.assert_called_once_with(
            api_key="test-key",
            timeout=30,
            max_retries=1,
        )
        create.assert_awaited_once()
        request = create.await_args.kwargs
        self.assertEqual(request["model"], "vision-test-model")
        self.assertIn("data:image/png;base64,", request["messages"][0]["content"][1]["image_url"]["url"])
        client.close.assert_awaited_once()


class VisionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rejects_non_image_upload(self):
        response = self.client.post(
            "/vision/analyze",
            files={"file": ("notes.txt", b"not an image", "text/plain")},
        )

        self.assertEqual(response.status_code, 415)
        self.assertIn("PNG, JPEG, or WebP", response.json()["detail"])

    def test_requires_confirmation_scope_by_rejecting_foreign_origin(self):
        response = self.client.post(
            "/vision/analyze",
            headers={"Origin": "https://untrusted.example"},
            files={"file": ("image.png", b"\x89PNG\r\n\x1a\ncontent", "image/png")},
        )

        self.assertEqual(response.status_code, 403)

    def test_analyzes_valid_image_without_persisting_upload(self):
        image = b"\x89PNG\r\n\x1a\ncontent"
        with patch(
            "app.services.vision_service.analyze_image",
            new=AsyncMock(return_value="A test image description."),
        ) as analyze:
            response = self.client.post(
                "/vision/analyze",
                files={"file": ("image.png", image, "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"analysis": "A test image description."})
        analyze.assert_awaited_once_with(image, "image/png")
        self.assertFalse((BASE_DIR / "static" / "uploads").exists())


if __name__ == "__main__":
    unittest.main()
