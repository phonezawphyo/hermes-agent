"""Tests for OpenViking memory provider - add_resource functionality.

Tests the fix for local file uploads and remote URL handling in viking_add_resource.
"""

import os
import json
import pytest
from unittest.mock import MagicMock, patch

from plugins.memory.openviking import OpenVikingMemoryProvider


class FakeOpenVikingClient:
    """Fake OpenViking client that simulates API responses."""

    def __init__(self):
        self.post_calls = []
        self.temp_uploads = {}

    def post(self, endpoint, json=None, files=None):
        """Mock POST request handler."""
        self.post_calls.append({
            "endpoint": endpoint,
            "json": json,
            "files": files is not None
        })

        if endpoint == "/api/v1/resources/temp_upload" and files:
            # Simulate temp upload
            temp_id = f"upload_test_{len(self.temp_uploads)}.md"
            self.temp_uploads[temp_id] = files
            return {
                "status": "ok",
                "result": {
                    "temp_file_id": temp_id
                }
            }

        elif endpoint == "/api/v1/resources":
            # Simulate resource addition
            if json and ("path" in json or "temp_file_id" in json):
                return {
                    "status": "ok",
                    "result": {
                        "status": "success",
                        "root_uri": f"viking://resources/test_{len(self.post_calls)}",
                        "errors": []
                    }
                }
            else:
                return {
                    "status": "error",
                    "result": {
                        "errors": ["Missing path or temp_file_id"]
                    }
                }

        return {"status": "error", "result": {}}


class TestOpenVikingAddResource:
    """Test suite for viking_add_resource tool."""

    def _make_provider(self):
        """Create a test provider with fake client."""
        provider = OpenVikingMemoryProvider()
        provider._client = FakeOpenVikingClient()
        provider._endpoint = "http://test:1933"
        provider._api_key = "test-key"
        return provider

    # ---------------------------------------------------------------------------
    # Test 1: Remote URL handling
    # ---------------------------------------------------------------------------

    def test_add_remote_url_uses_path_field(self):
        """Remote URLs should be sent with 'path' field."""
        provider = self._make_provider()

        result = provider._tool_add_resource({
            "path": "https://example.com/document.md",
            "reason": "Test remote URL"
        })

        result_json = json.loads(result)
        assert result_json["status"] == "added"
        assert result_json["root_uri"].startswith("viking://resources/")

        # Verify the client received 'path' not 'url'
        last_call = provider._client.post_calls[-1]
        assert "path" in last_call["json"]
        assert last_call["json"]["path"] == "https://example.com/document.md"
        assert last_call["json"]["reason"] == "Test remote URL"

    # ---------------------------------------------------------------------------
    # Test 2: Local file upload via temp_upload
    # ---------------------------------------------------------------------------

    def test_add_local_file_uploads_first(self, tmp_path):
        """Local files should be uploaded via temp_upload endpoint first."""
        # Create a temporary test file
        test_file = tmp_path / "test_document.md"
        test_file.write_text("# Test Document\n\nThis is test content.")

        provider = self._make_provider()

        result = provider._tool_add_resource({
            "path": str(test_file),
            "reason": "Test local file upload"
        })

        result_json = json.loads(result)
        assert result_json["status"] == "added"
        assert result_json["root_uri"].startswith("viking://resources/")

        # Verify temp_upload was called first
        assert len(provider._client.post_calls) == 2
        assert provider._client.post_calls[0]["endpoint"] == "/api/v1/resources/temp_upload"
        assert provider._client.post_calls[0]["files"] is True

        # Verify add_resource was called with temp_file_id
        assert provider._client.post_calls[1]["endpoint"] == "/api/v1/resources"
        assert "temp_file_id" in provider._client.post_calls[1]["json"]
        assert provider._client.post_calls[1]["json"]["reason"] == "Test local file upload"

    # ---------------------------------------------------------------------------
    # Test 3: Backward compatibility with 'url' field
    # ---------------------------------------------------------------------------

    def test_add_resource_supports_url_field_for_backward_compat(self):
        """Should support 'url' field for backward compatibility."""
        provider = self._make_provider()

        result = provider._tool_add_resource({
            "url": "https://example.com/old-format.md",
            "reason": "Test backward compatibility"
        })

        result_json = json.loads(result)
        assert result_json["status"] == "added"

        # The tool should map 'url' to 'path' internally
        last_call = provider._client.post_calls[-1]
        assert "path" in last_call["json"]
        assert last_call["json"]["path"] == "https://example.com/old-format.md"

    # ---------------------------------------------------------------------------
    # Test 4: Error handling - missing path/url
    # ---------------------------------------------------------------------------

    def test_add_resource_requires_path_or_url(self):
        """Should return error when neither path nor url is provided."""
        provider = self._make_provider()

        result = provider._tool_add_resource({
            "reason": "Missing path test"
        })

        assert "error" in result.lower() or "required" in result.lower()

    # ---------------------------------------------------------------------------
    # Test 5: Support for wait parameter
    # ---------------------------------------------------------------------------

    def test_add_resource_supports_wait_parameter(self):
        """Should pass wait parameter to the API."""
        provider = self._make_provider()

        result = provider._tool_add_resource({
            "path": "https://example.com/doc.md",
            "reason": "Test wait param",
            "wait": True
        })

        last_call = provider._client.post_calls[-1]
        assert last_call["json"]["wait"] is True

    # ---------------------------------------------------------------------------
    # Test 7: Support for optional parameters
    # ---------------------------------------------------------------------------

    def test_add_resource_passes_reason_and_wait(self):
        """Should pass reason and wait parameters."""
        provider = self._make_provider()

        result = provider._tool_add_resource({
            "path": "https://example.com/doc.md",
            "reason": "Custom reason",
            "wait": True
        })

        last_call = provider._client.post_calls[-1]
        assert last_call["json"]["reason"] == "Custom reason"
        assert last_call["json"]["wait"] is True
