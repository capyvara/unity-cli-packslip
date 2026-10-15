import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import discover_latest as discovery
from prepare_release import PLATFORMS


def manifest(version):
    return {
        "version": version,
        "binaries": {
            platform: {"filename": filename, "size": 1, "sha256": "a" * 64}
            for platform, (_, _, filename) in PLATFORMS.items()
        },
    }


def response(value):
    return io.BytesIO(json.dumps(value).encode())


def http_error(code):
    return urllib.error.HTTPError("https://example.com", code, "fixture", {}, None)


class DiscoveryTests(unittest.TestCase):
    def test_absent_channels_are_skipped_and_versions_are_deduplicated(self):
        with patch.object(discovery, "fetch", side_effect=[
            http_error(404), response(manifest("1.0.0-beta.13")),
            response(manifest("1.0.0-beta.13")),
        ]):
            self.assertEqual(discovery.latest_versions(), ["1.0.0-beta.13"])

    def test_all_absent_channels_fail_instead_of_silently_succeeding(self):
        with patch.object(discovery, "fetch", side_effect=http_error(404)):
            with self.assertRaisesRegex(ValueError, "No Unity CLI"):
                discovery.latest_versions()

    def test_channel_errors_and_invalid_metadata_fail(self):
        for error in (http_error(403), http_error(500), urllib.error.URLError("offline")):
            with self.subTest(error=error), patch.object(discovery, "fetch", side_effect=error):
                with self.assertRaises(urllib.error.URLError):
                    discovery.latest_versions()
        for value in ([], {}, {"version": "../escape"},
                      {"version": "1.0.0", "binaries": {}}, {"version": 1}):
            with self.subTest(value=value), patch.object(discovery, "fetch", return_value=response(value)):
                with self.assertRaises(ValueError):
                    discovery.latest_versions()
        with patch.object(discovery, "fetch", return_value=io.BytesIO(b"invalid JSON")):
            with self.assertRaises(ValueError):
                discovery.latest_versions()

    def test_only_unpublished_channel_versions_are_returned(self):
        def github_response(request, timeout):
            if request.full_url.endswith("/v1.0.0-beta.13"):
                return response({"tag_name": "v1.0.0-beta.13"})
            raise http_error(404)

        with patch.object(discovery, "fetch", side_effect=[
            response(manifest("1.0.0")), response(manifest("1.0.0-beta.13")),
            response(manifest("1.1.0-alpha.1")),
        ]), patch.object(discovery.urllib.request, "urlopen", side_effect=github_response):
            self.assertEqual(discovery.discover("owner/repo"), ["1.0.0", "1.1.0-alpha.1"])

    def test_existing_releases_produce_an_empty_matrix(self):
        with patch.object(discovery, "latest_versions", return_value=["1.0.0"]), \
                patch.object(discovery.urllib.request, "urlopen", return_value=response({"tag_name": "v1.0.0"})):
            self.assertEqual(discovery.discover("owner/repo"), [])

    def test_manual_version_does_not_fetch_channel_manifests(self):
        with patch.object(discovery, "fetch") as fetch, \
                patch.object(discovery.urllib.request, "urlopen", side_effect=http_error(404)):
            self.assertEqual(discovery.discover("owner/repo", "1.0.0"), ["1.0.0"])
        fetch.assert_not_called()

    def test_only_github_404_means_a_release_is_missing(self):
        for code in (401, 403, 429, 500):
            with self.subTest(code=code), \
                    patch.object(discovery.urllib.request, "urlopen", side_effect=http_error(code)):
                with self.assertRaises(urllib.error.HTTPError):
                    discovery.release_exists("owner/repo", "1.0.0")
        with patch.object(discovery.urllib.request, "urlopen", return_value=response({})):
            with self.assertRaises(ValueError):
                discovery.release_exists("owner/repo", "1.0.0")

    def test_github_request_encodes_tags_and_authenticates(self):
        version = "1.0.0+build.1"
        with patch.object(discovery.urllib.request, "urlopen", return_value=response({"tag_name": f"v{version}"})) as urlopen:
            self.assertTrue(discovery.release_exists("owner/repo", version, token="test-token"))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/repos/owner/repo/releases/tags/v1.0.0%2Bbuild.1")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_invalid_repository_or_version_is_rejected_before_network_access(self):
        with patch.object(discovery, "fetch") as fetch, \
                patch.object(discovery.urllib.request, "urlopen") as urlopen:
            for repository, version in (("owner/repo?redirect=elsewhere", None), ("owner/repo", "../escape")):
                with self.assertRaises(ValueError):
                    discovery.discover(repository, version)
        fetch.assert_not_called()
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
