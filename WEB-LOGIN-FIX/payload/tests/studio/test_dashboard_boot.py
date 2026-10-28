"""Guard against server-side errors during the first authenticated Web load."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from sqw.studio.server import Application
from sqw.studio.settings import Settings


class DashboardBootSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Application(Settings(Path(self.temp.name)))
        self.app.auth.setup(
            self.app.auth.setup_token(),
            "owner@example.org", "Test Administrator", "correct horse battery staple"
        )
        self.token, self.csrf, _ = self.app.auth.login(
            "owner@example.org", "correct horse battery staple", "127.0.0.1"
        )

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, authenticated=True):
        env = {
            "REQUEST_METHOD": "GET", "PATH_INFO": path, "QUERY_STRING": "",
            "HTTP_HOST": "127.0.0.1:8000", "wsgi.input": io.BytesIO(b""),
            "CONTENT_LENGTH": "0", "REMOTE_ADDR": "127.0.0.1"
        }
        if authenticated:
            env["HTTP_COOKIE"] = "sqe_session=" + self.token
        response = {}

        def start(status, headers):
            response["status"] = int(status.split()[0])
            response["headers"] = dict(headers)

        stream = self.app(env, start)
        try:
            data = b"".join(stream)
        finally:
            if hasattr(stream, "close"):
                stream.close()
        response["json"] = json.loads(data)
        return response

    def test_authenticated_initial_dashboard_api_calls(self):
        # Reproduces the request sequence emitted immediately after successful login.
        for path in ("/api/projects", "/api/macros", "/api/template", "/api/capabilities"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)["status"], 200)

    def test_template_contains_valid_project_model(self):
        template = self.request("/api/template")
        self.assertEqual(template["status"], 200)
        self.assertIn("config", template["json"])
        self.assertIn("process", template["json"])

    def test_parametric_preset_uses_same_document(self):
        response = self.request("/api/quantumlab/parametric-preset")
        self.assertEqual(response["status"], 200)
        self.assertEqual(response["json"]["schema_version"], 2)

    def test_template_requires_authentication(self):
        self.assertEqual(self.request("/api/template", authenticated=False)["status"], 401)


if __name__ == "__main__":
    unittest.main()
