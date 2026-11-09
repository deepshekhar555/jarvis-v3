"""User-initiated image analysis through the configured OpenAI model."""

import base64
import logging

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 8 * 1024 * 1024


class VisionConfigurationError(RuntimeError):
    """The vision feature cannot run with the current configuration."""


class VisionProviderError(RuntimeError):
    """The configured model could not complete image analysis."""


def detect_image_media_type(image: bytes) -> str:
    """Validate image size and identify a supported type from its content."""
    if not image:
        raise ValueError("The uploaded image is empty.")
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("Images must be 8 MB or smaller.")
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if (
        len(image) >= 12
        and image.startswith(b"RIFF")
        and image[8:12] == b"WEBP"
    ):
        return "image/webp"
    raise ValueError("Use a valid PNG, JPEG, or WebP image.")


async def analyze_image(image: bytes, media_type: str) -> str:
    """Send an in-memory image to the configured vision-capable model."""
    from config import OPENAI_API_KEY, OPENAI_MODEL

    if not OPENAI_API_KEY:
        raise VisionConfigurationError(
            "Image analysis is unavailable: OPENAI_API_KEY is not configured."
        )

    from openai import APIError, AsyncOpenAI

    image_data = base64.b64encode(image).decode("ascii")
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=30, max_retries=1)
    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe this image accurately. Note uncertainty and do not identify people.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_data}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=500,
        )
    except APIError as error:
        from app.services.provider_errors import describe_provider_error

        logger.error(
            "Image analysis provider failed (%s, status %s)",
            type(error).__name__,
            getattr(error, "status_code", "unknown"),
        )
        raise VisionProviderError(
            describe_provider_error(error)
        ) from error
    finally:
        await client.close()

    if not response.choices or not response.choices[0].message.content:
        raise VisionProviderError("The image analysis provider returned no description.")
    return response.choices[0].message.content
