import unittest
from uuid import uuid4

from support import raw_request, request

from sentinel.main import app


class WorkbenchTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_serves_workbench_without_database_access(self):
        status, headers, content = await raw_request(app, "/")
        self.assertEqual(status, 200)
        self.assertIn(b"text/html", headers[b"content-type"])
        self.assertIn(b">Incidents</h1>", content)
        self.assertIn(b"/static/app.js", content)
        self.assertIn(b"frame-ancestors 'none'", headers[b"content-security-policy"])
        self.assertEqual(headers[b"cache-control"], b"no-store")

    async def test_incident_links_render_a_validated_selection(self):
        incident_id = uuid4()
        status, _, content = await raw_request(app, f"/incidents/{incident_id}")
        self.assertEqual(status, 200)
        self.assertIn(f'data-incident-id="{incident_id}"'.encode(), content)
        status, _ = await request(app, "/incidents/not-a-uuid")
        self.assertEqual(status, 422)

    async def test_assets_are_served_from_application(self):
        for path, expected in (
            ("/static/app.js", b"refreshOverview"),
            ("/static/format.js", b"escapeHTML"),
            ("/static/workbench.css", b"prefers-reduced-motion"),
            ("/static/vendor/tabler-1.7.0.min.css", b"Tabler v1.7.0"),
        ):
            status, _, content = await raw_request(app, path)
            self.assertEqual(status, 200, path)
            self.assertIn(expected, content)
        status, _, _ = await raw_request(app, "/static/missing.js")
        self.assertEqual(status, 404)

    async def test_health_stays_a_dependency_free_json_response(self):
        status, body = await request(app, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "ok"})

    async def test_workbench_has_no_operator_controls_or_credentials(self):
        status, _, content = await raw_request(app, "/")
        self.assertEqual(status, 200)
        self.assertNotIn(b"operator-token", content)
        self.assertNotIn(b"producer-form", content)
        self.assertNotIn(b"operator-button", content)
        self.assertNotIn(b"csrf", content)
        self.assertIn(b'id="view-detail" class="view-panel" hidden', content)
        self.assertIn(
            b'id="view-stream" class="view-panel stream-view" hidden', content
        )

    async def test_interface_uses_contract_neutral_labels(self):
        status, _, content = await raw_request(app, "/")
        self.assertEqual(status, 200)
        for value in (
            b"Timestamp violations",
            b"Raw event_time",
            b"Synthetic orders",
            b"poll-state",
        ):
            self.assertNotIn(value, content)
        self.assertIn(b"Producer / revision", content)

    async def test_stream_and_contracts_have_separate_addresses(self):
        for path in ("/stream", "/contracts"):
            status, _, content = await raw_request(app, path)
            self.assertEqual(status, 200)
            self.assertIn(b"/static/app.js", content)

    async def test_no_workbench_mutation_routes_are_exposed(self):
        status, _, _ = await raw_request(
            app, "/workbench/producer/configuration", method="PATCH"
        )
        self.assertEqual(status, 404)
        status, _, _ = await raw_request(
            app, f"/workbench/incidents/{uuid4()}/investigations/retry", method="POST"
        )
        self.assertEqual(status, 404)
