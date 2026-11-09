"""Image generation and local asset persistence."""

from datetime import datetime


def generate_image_asset(prompt: str) -> str:
    """Generate an image through OpenAI and save it under the static assets."""
    from config import BASE_DIR, OPENAI_API_KEY
    from openai import OpenAI
    import requests

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size="1024x1024",
        quality="standard",
        n=1,
    )
    if not response.data:
        raise RuntimeError("The image provider returned no image.")
    image_url = response.data[0].url
    if not image_url:
        raise RuntimeError("The image provider returned no image URL.")
    image_response = requests.get(image_url, timeout=30)
    image_response.raise_for_status()
    image_data = image_response.content
    if not image_data:
        raise RuntimeError("The image provider returned an empty image.")

    filename = f"gen_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    save_dir = BASE_DIR / "static" / "generated_images"
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / filename
    save_path.write_bytes(image_data)
    return f"/static/generated_images/{filename}"
