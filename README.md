# Unity CLI Packslip

Install the official Unity CLI through mise using signed, third-party Packslip
metadata maintained in `capyvara/unity-cli-packslip`.

This repository describes Unity's existing binaries and keeps their original
versioned download URLs. Each release checks all six binaries against the SHA-256
digests and sizes in Unity's version manifest, then signs a Packslip as
`repackager`. The signature identifies this packaging project; Unity remains the
binary publisher. This project does not build Unity CLI or provide Unity build
provenance.

Supported downloads are macOS, Linux, and Windows on ARM64 and x64. Packslip reads
host library requirements from the binaries. Linux downloads require glibc 2.34
or newer, matching Unity's installer; these releases do not provide a musl/Alpine build. Installing the CLI does not
install a Unity Editor or activate a Unity license.

## Install with mise

Use a recent mise release with the Packslip backend. To install the latest
published version, including Unity's prereleases:

```sh
mise use 'packslip:github.com/capyvara/unity-cli-packslip[prerelease=true]@latest'
```

Or add this to `mise.toml` (with an optional workflow signer pin):

```toml
[tools."packslip:github.com/capyvara/unity-cli-packslip"]
version = "latest"
prerelease = true
workflow = "release.yml@refs/heads/main"
```

Then install and verify the active CLI:

```sh
mise install
mise exec -- unity --version
```

Mise excludes prereleases by default. While this repository has only prereleases,
omitting `prerelease=true` produces `no versions found`; GitHub's
`/releases/latest` endpoint also returns HTTP 404. A separate `latest` tag is not
needed. Once stable versions are published, the plain tool name can select them.

Only Unity versions with a signed release in this repository are available.
Fresh releases may be hidden from `latest` and `mise ls-remote` by mise's
`minimum_release_age` setting; an exact version installs immediately. To opt into
fresh releases for one invocation, prefix the command with
`MISE_MINIMUM_RELEASE_AGE=0s`.
For reproducible installs, use an exact version such as `1.0.0-beta.13` or generate
and commit `mise.lock` with `mise lock`, then use `mise install --locked`.

The `workflow` option pins the repository's release workflow on `main`.
GitHub Actions signs with its OIDC identity, so no long-lived signing key is
needed. The verified repository signer fingerprint is:

```text
ps1_mpg4wf4wjxgobv2w4b3xf45cia
```

To check a downloaded release bundle against that fingerprint:

```sh
packslip verify packslip.sigstore.json \
  --pin ps1_mpg4wf4wjxgobv2w4b3xf45cia \
  --identity https://github.com/capyvara/unity-cli-packslip/.github/workflows/release.yml@refs/heads/main \
  --issuer https://token.actions.githubusercontent.com
```

## Prepare and check locally

Python 3.11+ and mise are required. Python uses only the standard library;
Packslip and the workflow linter are pinned in `mise.toml`.

```sh
mise trust
mise install
mise run check
mise run prepare 1.0.0-beta.13
```

Preparation downloads the exact version's `latest.json` (not a moving channel
manifest), verifies all six original binaries, and writes these files under
`build/1.0.0-beta.13/`:

- `release.toml`: Packslip input with platform mappings and original CDN URLs.
- `upstream-manifest.json`: the Unity manifest whose checksums were checked.
- `release-notes.md`: notes for the GitHub release.
- The six downloaded binaries, retained locally for digest verification.

Cached binaries are checked before reuse. Preparation fails on missing platforms,
unexpected filenames, a mismatched version, invalid metadata, or corrupt/truncated
downloads. Stale preparation metadata is removed before starting again.

To create a local test bundle without publishing to a transparency log:

```sh
mkdir -p work/local-signing
mise exec -- packslip keygen --out work/local-signing/release.key
mise exec -- packslip create \
  --manifest build/1.0.0-beta.13/release.toml \
  --attested-by repackager \
  --evidence checksum-file-over-tls=https://public-cdn.cloud.unity3d.com/hub/prod/cli/1.0.0-beta.13/latest.json \
  --key work/local-signing/release.key --no-log \
  --out build/1.0.0-beta.13/local-packslip
mise exec -- packslip verify \
  build/1.0.0-beta.13/local-packslip/packslip.sigstore.json \
  --pubkey work/local-signing/release.pub --allow-unlogged \
  --artifact build/1.0.0-beta.13/unity-darwin-arm64 \
  --artifact build/1.0.0-beta.13/unity-darwin-x64 \
  --artifact build/1.0.0-beta.13/unity-linux-arm64 \
  --artifact build/1.0.0-beta.13/unity-linux-x64 \
  --artifact build/1.0.0-beta.13/unity-windows-arm64.exe \
  --artifact build/1.0.0-beta.13/unity-windows-x64.exe
```

The generated key and test bundle stay in ignored directories. These local tests
check the manifest, signature, and binary digests; GitHub discovery and OIDC
verification require a published release and are separate checks.

## Publish a release

Only the initial publication requires explicit owner approval. Subsequent
releases may be signed and published automatically by CI, including public
signing/log entries, after checks and binary verification pass. No per-release
approval is required.

The `Publish Unity CLI Packslip` workflow checks daily at 09:17 UTC (06:17 in
São Paulo). It reads Unity's `latest.json`, `latest-beta.json`, and
`latest-alpha.json` channel manifests and publishes any versions without an
existing GitHub release. Missing channels (HTTP 404) are skipped; network errors
and invalid manifests fail the run. Duplicate versions are published only once.
Only the current channel versions are checked; older releases are not backfilled,
and versions replaced between daily checks may be missed.

The workflow can also be dispatched manually on `main`: leave the version empty
to check the latest channels, or provide an exact Unity CLI version. Pushes and
pull requests run checks only. The daily schedule takes effect once the workflow
is on the repository's default branch (`main`).

To preview pending versions locally without downloading binaries or publishing:

```sh
python3 scripts/discover_latest.py --repository capyvara/unity-cli-packslip
```

The release workflow:

1. Runs the unit tests and workflow linter.
2. Downloads and checks all six Unity binaries from the version manifest.
3. Signs the Packslip as `repackager`, recording the Unity manifest URL as evidence.
4. Verifies the exact workflow identity and all six artifact digests.
5. Creates `v<VERSION>` and uploads `packslip.sigstore.json` plus
   `upstream-manifest.json` to a GitHub release. Unity binaries stay on Unity's CDN.

The repository needs GitHub Actions enabled and permission for the workflow to
write releases and request OIDC tokens. The workflow runs only from `main` and
marks versions with prerelease identifiers as GitHub prereleases. Existing
releases are not overwritten. Every new Unity version requires a new publication.
Preparation also checks `GLIBC_MIN` in Unity's official installer against
`scripts/prepare_release.py`. A changed or missing value stops publication for
maintainer review of the Linux requirements.

After the first publication, validate real mise discovery and installation:

```sh
mise ls-remote 'packslip:github.com/capyvara/unity-cli-packslip[prerelease=true,workflow=release.yml@refs/heads/main]'
mise use 'packslip:github.com/capyvara/unity-cli-packslip[workflow=release.yml@refs/heads/main]@1.0.0-beta.13'
mise exec -- unity --version
```

Unity CLI binaries retain Unity's licensing terms. The MIT license in this
repository applies to this project's scripts and documentation.

## References

- [Unity CLI](https://docs.unity.com/en-us/unity-cli)
- [Packslip repackager attestations](https://packslip.dev/release/v1/#repackager-attestation)
- [Packslip artifact configuration](https://packslip.dev/docs/describing-releases/)
- [mise Packslip backend](https://mise.jdx.dev/dev-tools/backends/packslip.html)
