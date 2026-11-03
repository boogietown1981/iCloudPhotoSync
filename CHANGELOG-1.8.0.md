# v1.8.0 Stability and Security

Base: main @ 5a25bc08af3d050d088962a55cb1ce54d7b15576

## Data integrity
- Report sync as failed if any photo fails or CloudKit pagination cannot be enumerated.
- Reject truncated download bodies using Content-Length, and validate original asset size when available.
- Stage cross-volume moves to a temporary file, compare SHA-256, create destination without clobber, then update manifest before deleting source.
- Report incomplete moves as errors and constrain move destinations to the configured account path.

## Access control and packaging
- Require DSM administrators for all CGI operations, including sensitive exports.
- Hide the DSM app from non-admin users.
- Remove automatic NOPASSWD sudoers grant rules from standalone package lifecycle.
- Align both build tracks on 1.8.0 and add regression/syntax CI.

## Deployment
- Existing manifests remain compatible; no schema migration.
- Back up `/var/packages/iCloudPhotoSync/var` before upgrading.
- Manually grant the package user access to the destination share.
- Remove any legacy `/etc/sudoers.d/iCloudPhotoSync` privileges with administrator access if package installation cannot.
- Verify on a test NAS and a sample library before production adoption.

## Deferred
- A low-memory streaming ZIP export.
- Persistent end-to-end local content hashes for periodic verification.
- Vendor dependency refresh and reproducible multi-arch SPK release.
