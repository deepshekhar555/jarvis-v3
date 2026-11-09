import unittest

from app.services.provider_errors import describe_provider_error


class ProviderException(Exception):
    status_code: int

    def __init__(self, status_code: int):
        self.status_code = status_code


class ProviderErrorMessageTests(unittest.TestCase):
    def test_authentication_errors_point_to_local_configuration(self):
        error = ProviderException(401)

        message = describe_provider_error(error)

        self.assertIn("OPENAI_API_KEY", message)
        self.assertIn(".env", message)
        self.assertNotIn("API key value", message)

    def test_rate_limit_and_server_errors_are_actionable(self):
        rate_limit = ProviderException(429)
        server_error = ProviderException(503)

        self.assertIn("quota", describe_provider_error(rate_limit))
        self.assertIn("temporarily unavailable", describe_provider_error(server_error))

    def test_connection_errors_do_not_expose_raw_details(self):
        error = type("APIConnectionError", (Exception,), {})("private request detail")

        message = describe_provider_error(error)

        self.assertIn("internet connection", message)
        self.assertNotIn("private request detail", message)


if __name__ == "__main__":
    unittest.main()
