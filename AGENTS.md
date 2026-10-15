# Project instructions

This project publishes third-party Packslip metadata for Unity CLI.

- Ask the user before the initial GitHub publication. After that, CI may sign
  and publish subsequent releases, including public signing/log entries,
  without per-release approval. Local changes, downloads, tests, and unlogged
  local signing are permitted.
- Keep Unity binaries at their original versioned CDN URLs. Verify every
  downloaded binary against the checksum and size in Unity's version manifest.
- Sign as `repackager` and record the evidence checked. Do not claim that this
  project built Unity CLI or that its signature belongs to Unity.
- CI may sign and publish releases after checks pass and all downloaded
  binaries have been verified against Unity's version manifest.
- Run `mise run check` after changes. Keep generated downloads, signing keys,
  and local bundles out of Git.
- Keep README.md and AGENTS.md under 200 lines.
