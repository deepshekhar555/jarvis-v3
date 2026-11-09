"""Safe user-facing messages for external model-provider failures."""


def describe_provider_error(error: Exception) -> str:
    """Translate provider errors without including request secrets or raw details."""
    status_code = getattr(error, "status_code", None)
    if status_code in {401, 403}:
        return (
            "The AI provider rejected the configured API key or its permissions. "
            "Update OPENAI_API_KEY in the project .env file, then restart J.A.R.V.I.S."
        )
    if status_code == 429:
        return (
            "The AI provider rate limit or usage quota was reached. "
            "Check the provider account and try again later."
        )
    if isinstance(status_code, int) and status_code >= 500:
        return "The AI provider is temporarily unavailable. Please try again later."
    if type(error).__name__ in {"APIConnectionError", "APITimeoutError", "TimeoutException"}:
        return "Could not connect to the AI provider. Check your internet connection and try again."
    return "I encountered an unexpected AI provider error. Please try again."
