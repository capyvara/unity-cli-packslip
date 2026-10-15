import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "prepare_release", Path(__file__).resolve().parents[1] / "scripts/prepare_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
VERSION = "1.0.0-beta.13"
BINARY = b"a verified binary fixture"
INSTALLER = b'GLIBC_MIN="2.34"\n'


def upstream_manifest():
    return {
        "version": VERSION,
        "binaries": {
            platform: {"filename": filename, "size": len(BINARY),
                       "sha256": hashlib.sha256(BINARY).hexdigest()}
            for platform, (_, _, filename) in release.PLATFORMS.items()
        },
    }


class PreparationTests(unittest.TestCase):
    def test_version_must_be_pinned_semver(self):
        for value in ("latest", "beta", "../escape", "1.0.0;touch x", "01.0.0", "1.0.0-beta.01"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                release.validate_version(value)
        self.assertEqual(release.validate_version(VERSION), VERSION)

    def test_manifest_rejects_wrong_version_missing_platform_and_invalid_metadata(self):
        changes = (
            lambda manifest: manifest.update(version="1.0.0"),
            lambda manifest: manifest["binaries"].pop("linux-x64"),
            lambda manifest: manifest["binaries"]["darwin-arm64"].update(filename="../escape"),
            lambda manifest: manifest["binaries"]["darwin-arm64"].update(sha256="invalid"),
            lambda manifest: manifest["binaries"]["darwin-arm64"].update(size=True),
        )
        for change in changes:
            manifest = copy.deepcopy(upstream_manifest())
            change(manifest)
            with self.assertRaises(ValueError):
                release.validate_manifest(manifest, VERSION)

    def test_download_rejects_tampered_and_truncated_binaries(self):
        entry = upstream_manifest()["binaries"]["darwin-arm64"]
        for payload in (b"wrong" + BINARY[5:], BINARY[:-1], BINARY + b"extra"):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / entry["filename"]
                with patch.object(release, "fetch", return_value=io.BytesIO(payload)):
                    with self.assertRaises(ValueError):
                        release.download_binary("https://example.com/binary", target, entry)
                self.assertFalse(target.exists())
                self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_preparation_maps_all_six_platforms_to_original_cdn_urls(self):
        manifest = upstream_manifest()
        def response(url):
            if url.endswith("install.sh"):
                return io.BytesIO(INSTALLER)
            return io.BytesIO(json.dumps(manifest).encode() if url.endswith("latest.json") else BINARY)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "build"
            with patch.object(release, "fetch", side_effect=response):
                release.prepare(VERSION, output)
            parsed = tomllib.loads((output / "release.toml").read_text())
            self.assertEqual(parsed["project"], release.PROJECT)
            self.assertNotIn("source", parsed)
            self.assertEqual(parsed["bin"], ["unity"])
            self.assertEqual(len(parsed["artifact"]), 6)
            for artifact, (os_name, arch, filename) in zip(parsed["artifact"], release.PLATFORMS.values()):
                self.assertEqual((artifact["os"], artifact["arch"], artifact["format"]), (os_name, arch, "raw"))
                self.assertEqual(artifact["url"], f"{release.CDN_BASE}/{VERSION}/{filename}")
                self.assertEqual(Path(artifact["path"]).read_bytes(), BINARY)
                if os_name == "linux":
                    self.assertEqual(artifact["requires"]["glibc_min"], "2.34")

    def test_failed_preparation_removes_stale_signing_metadata(self):
        manifest = upstream_manifest()
        def response(url):
            if url.endswith("install.sh"):
                return io.BytesIO(INSTALLER)
            return io.BytesIO(json.dumps(manifest).encode() if url.endswith("latest.json") else b"corrupt")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "release.toml").write_text("stale")
            with patch.object(release, "fetch", side_effect=response):
                with self.assertRaises(ValueError):
                    release.prepare(VERSION, output)
            self.assertFalse((output / "release.toml").exists())

    def test_linux_requirement_changes_stop_preparation_before_downloading_binaries(self):
        for installer in (b'GLIBC_MIN="2.35"\n', b"installer with no GLIBC_MIN"):
            with self.subTest(installer=installer), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                with patch.object(release, "fetch", side_effect=[
                    io.BytesIO(json.dumps(upstream_manifest()).encode()), io.BytesIO(installer),
                ]) as fetch:
                    with self.assertRaisesRegex(ValueError, "review Linux requirements"):
                        release.prepare(VERSION, output)
                self.assertEqual(fetch.call_count, 2)
                self.assertFalse((output / "release.toml").exists())

    def test_manifest_fetch_failure_removes_stale_signing_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output / "release.toml").write_text("stale")
            with patch.object(release, "fetch", side_effect=OSError("network unavailable")):
                with self.assertRaises(OSError):
                    release.prepare(VERSION, output)
            self.assertFalse((output / "release.toml").exists())


if __name__ == "__main__":
    unittest.main()
