# Project instructions

This project publishes third-party Packslip metadata for Unity CLI.

- Ask the user before any GitHub publication: repository creation, pushes,
  pull requests, releases, workflow dispatches, or public signing/log entries.
  Local changes, downloads, tests, and unlogged local signing are permitted.
- Keep Unity binaries at their original versioned CDN URLs. Verify every
  downloaded binary against the checksum and size in Unity's version manifest.
- Sign as `repackager` and record the evidence checked. Do not claim that this
  project built Unity CLI or that its signature belongs to Unity.
- Publishing must be an explicit manual action. CI checks must not sign or
  publish releases.
- Run `mise run check` after changes. Keep generated downloads, signing keys,
  and local bundles out of Git.
- Keep README.md and AGENTS.md under 200 lines.
