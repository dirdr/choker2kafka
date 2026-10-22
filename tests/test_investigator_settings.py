import os
import unittest
from unittest.mock import MagicMock, patch

from support import request

from sentinel.investigation.settings import SettingsConflict
from sentinel.main import app


class InvestigatorSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repository = MagicMock()
        self.current = {
            "revision": 3,
            "model_id": "claude-haiku-4-5-20251001",
            "token_limit": 50000,
        }
        self.change = {
            "expected_revision": 3,
            "model_id": "claude-sonnet-4-6",
            "token_limit": 80000,
        }
        self.repository.settings.return_value = self.current
        self.repository.update_settings.return_value = {
            "revision": 4,
            **{k: v for k, v in self.change.items() if k != "expected_revision"},
        }
        app.state.investigation_repository = self.repository
        self.addCleanup(lambda: delattr(app.state, "investigation_repository"))
        self.env = patch.dict(os.environ, {"OPERATOR_TOKEN": "server-only-test-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)
        catalog = patch(
            "sentinel.workbench.settings.available_models",
            return_value=[{"id": "claude-sonnet-4-6", "name": "Claude Sonnet"}],
        )
        catalog.start()
        self.addCleanup(catalog.stop)

    async def browser_headers(self):
        status, body = await request(app, "/workbench/investigator/settings")
        self.assertEqual(status, 200)
        self.assertNotIn("server-only-test-secret", str(body))
        return [
            (b"origin", b"http://test"),
            (b"sec-fetch-site", b"same-origin"),
            (b"x-sentinel-csrf", body["csrf_token"].encode()),
        ]

    async def test_browser_saves_without_exposing_operator_credentials(self):
        headers = await self.browser_headers()
        status, body = await request(
            app,
            "/workbench/investigator/settings",
            method="PATCH",
            body=self.change,
            extra_headers=headers,
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["revision"], 4)
        self.assertEqual(
            self.repository.update_settings.call_args.args[0].model_id,
            self.change["model_id"],
        )

    async def test_missing_forged_expired_or_cross_origin_tokens_cannot_write(self):
        headers = await self.browser_headers()
        for invalid in (
            [],
            [
                (key, b"https://outside.test" if key == b"origin" else value)
                for key, value in headers
            ],
            [
                (key, b"forged" if key == b"x-sentinel-csrf" else value)
                for key, value in headers
            ],
            [
                (key, b"cross-site" if key == b"sec-fetch-site" else value)
                for key, value in headers
            ],
        ):
            status, _ = await request(
                app,
                "/workbench/investigator/settings",
                method="PATCH",
                body=self.change,
                extra_headers=invalid,
            )
            self.assertEqual(status, 403)
        with patch("sentinel.workbench.access.time", return_value=99999999999):
            status, _ = await request(
                app,
                "/workbench/investigator/settings",
                method="PATCH",
                body=self.change,
                extra_headers=headers,
            )
        self.assertEqual(status, 403)
        self.repository.update_settings.assert_not_called()

    async def test_stale_settings_return_a_conflict(self):
        self.repository.update_settings.side_effect = SettingsConflict()
        status, _ = await request(
            app,
            "/workbench/investigator/settings",
            method="PATCH",
            body=self.change,
            extra_headers=await self.browser_headers(),
        )
        self.assertEqual(status, 409)

    async def test_settings_validation_rejects_invalid_model_and_budget(self):
        headers = await self.browser_headers()
        for invalid in (
            {"model_id": "openai:test"},
            {"token_limit": 100001},
            {"token_limit": True},
            {"expected_revision": -1},
            {"producer_id": "checkout"},
        ):
            status, _ = await request(
                app,
                "/workbench/investigator/settings",
                method="PATCH",
                body={**self.change, **invalid},
                extra_headers=headers,
            )
            self.assertEqual(status, 422)
        self.repository.update_settings.assert_not_called()

    async def test_public_api_requires_bearer_token(self):
        status, _ = await request(
            app, "/api/investigation/settings", method="PATCH", body=self.change
        )
        self.assertEqual(status, 401)
        status, _ = await request(
            app,
            "/api/investigation/settings",
            method="PATCH",
            body=self.change,
            token="server-only-test-secret",
        )
        self.assertEqual(status, 200)

    async def test_catalog_failure_keeps_current_settings_available(self):
        with patch(
            "sentinel.workbench.settings.available_models",
            side_effect=OSError("secret"),
        ):
            status, body = await request(app, "/workbench/investigator/settings")
        self.assertEqual(status, 200)
        self.assertEqual(body["settings"], self.current)
        self.assertEqual(body["models"], [])
        self.assertNotIn("secret", str(body))

    async def test_missing_server_token_disables_browser_changes(self):
        with patch.dict(os.environ, {"OPERATOR_TOKEN": ""}):
            status, body = await request(app, "/workbench/investigator/settings")
            self.assertEqual(status, 200)
            self.assertFalse(body["editable"])
            self.assertIsNone(body["csrf_token"])
            status, _ = await request(
                app,
                "/workbench/investigator/settings",
                method="PATCH",
                body=self.change,
            )
        self.assertEqual(status, 503)
