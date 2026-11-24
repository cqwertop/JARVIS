"""Other companies' AI services (OpenAI-compatible APIs), tested against a fake local server - no real keys or costs."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

import brains
import providers
import settings
import tools


class FakeAPI(BaseHTTPRequestHandler):
    """Behaves like /v1 of an OpenAI-compatible service. Key 'good' works, anything else is rejected."""

    requests: list[dict] = []
    reject_tools = False

    def log_message(self, *args):
        pass

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self):
        if self.headers.get("Authorization") != "Bearer good":
            self._send(401, {"error": {"message": "Incorrect API key provided"}})
            return False
        return True

    def do_GET(self):
        if self._authorised() and self.path.endswith("/models"):
            ids = ["gpt-5-mini", "gpt-5", "text-embedding-3-small", "whisper-1", "tts-1", "models/gemini-2.5-flash"]
            self._send(200, {"data": [{"id": i} for i in ids]})

    def do_POST(self):
        # Read the body before answering: on Windows, closing a socket with unread data resets the connection.
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if not self._authorised():
            return
        FakeAPI.requests.append(body)
        if FakeAPI.reject_tools and "tools" in body:
            self._send(400, {"error": {"message": "This model does not support tools"}})
            return
        last = body["messages"][-1]
        if last["role"] == "user" and "time" in last["content"] and "tools" in body:
            msg = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "get_current_time", "arguments": "{}"}}]}
        elif last["role"] == "tool":
            msg = {"role": "assistant", "content": f"The tool said: {last['content']}"}
        else:
            msg = {"role": "assistant", "content": "<think>hmm</think>Hello, sir."}
        self._send(200, {"choices": [{"message": msg}]})


class ProvidersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeAPI)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1"
        tools.init(settings.load())

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeAPI.requests.clear()
        FakeAPI.reject_tools = False

    def test_every_provider_is_complete(self):
        for pid, info in providers.PROVIDERS.items():
            for field in ("label", "kind", "base_url", "key_prefix", "key_url", "site", "blurb", "prefer"):
                self.assertIn(field, info, pid)
            if pid not in ("custom",):
                self.assertTrue(info["key_url"].startswith("https://"), pid)
        self.assertEqual(providers.credential_name("anthropic"), "anthropic_api_key")
        self.assertEqual(providers.credential_name("openai"), "openai_api_key")

    def test_list_models_keeps_only_chat_models(self):
        models = providers.list_models(self.url, "good", "Fake")
        self.assertEqual(models, ["gemini-2.5-flash", "gpt-5", "gpt-5-mini"])
        self.assertEqual(providers.suggest_model("openai", models), "gpt-5-mini")

    def test_bad_key_gives_a_friendly_message(self):
        with self.assertRaises(providers.ProviderError) as cm:
            providers.list_models(self.url, "wrong", "Fake")
        self.assertIn("key", str(cm.exception).lower())
        self.assertNotIn("Traceback", str(cm.exception))

    def test_brain_uses_tools_and_strips_thinking(self):
        brain = brains.OpenAICompatBrain(self.url, "good", "gpt-5-mini", "You are JARVIS.", label="Fake")
        reply = brain.ask("what time is it")
        self.assertTrue(reply.startswith("The tool said:"), reply)
        self.assertEqual([m["role"] for m in brain.history], ["user", "assistant", "tool", "assistant"])
        self.assertEqual(brain.history[2]["tool_call_id"], "call_1")
        self.assertEqual(FakeAPI.requests[0]["messages"][0], {"role": "system", "content": "You are JARVIS."})
        self.assertEqual(brain.ask("hi"), "Hello, sir.")

    def test_model_without_tools_still_talks(self):
        FakeAPI.reject_tools = True
        brain = brains.OpenAICompatBrain(self.url, "good", "tiny", "You are JARVIS.", label="Fake")
        self.assertEqual(brain.ask("hi"), "Hello, sir.")
        self.assertNotIn("tools", FakeAPI.requests[-1])

    def test_bad_key_while_talking_is_explained(self):
        brain = brains.OpenAICompatBrain(self.url, "wrong", "gpt-5-mini", "You are JARVIS.", label="Fake")
        with self.assertRaises(RuntimeError) as cm:
            brain.ask("hi")
        self.assertIn("Fake", str(cm.exception))

    def test_make_online_brain_needs_a_saved_key(self):
        s = settings.load()
        s = {**s, "online": {"provider": "openai", "model": "gpt-5-mini", "base_url": ""}}
        import credentials

        original = credentials.get
        try:
            credentials.get = lambda account: None
            with self.assertRaises(RuntimeError) as cm:
                brains.make_online_brain(s, "x")
            self.assertIn("No OpenAI API key", str(cm.exception))
            credentials.get = lambda account: "good" if account == "openai_api_key" else None
            brain = brains.make_online_brain({**s, "online": {**s["online"], "base_url": self.url}}, "x")
            self.assertEqual(brain.base_url, self.url)
        finally:
            credentials.get = original


if __name__ == "__main__":
    unittest.main()
