# Code signing, licensing and antivirus

Goal: every TrueDuty download opens without "unknown publisher" or antivirus warnings, and anyone can check that a file came from this repository.

## What the build already does (no setup needed)

| Measure | Why it helps |
|---|---|
| Nuitka **standalone** folders, never one-file builds | One-file executables unpack themselves to a temp folder on every start. Packers used by malware do the same, so antivirus heuristics flag it. A plain folder installed by a normal installer is what every commercial app ships. |
| Real installers (Inno Setup, dmg/pkg, deb/rpm) | Installed apps in Program Files / Applications / /opt look normal to Defender and Gatekeeper. |
| Full version resource on Windows files (company, product, version, copyright) | Files without metadata score worse in reputation systems. |
| No UPX or other packers | Packed binaries are a top false positive cause. |
| Sigstore build provenance on every file | `gh attestation verify <file> --repo QudsLab/TrueDuty` proves the file was built by this workflow from a given commit. |
| `SHA256SUMS.txt` and `.sha256` per file | Detects a corrupted or swapped download. |
| macOS ad hoc signature | Apple silicon refuses to start completely unsigned code. |
| MIT `LICENSE` + `THIRD_PARTY_NOTICES.md` inside every package, licence page in the Windows installer | Licensing of the app and every bundled component is clear. |

## Windows Authenticode (removes "Unknown publisher", stops most SmartScreen and AV warnings)

The workflow uses the first option whose secrets exist.

1. **SignPath Foundation (free for open source, recommended).**
   Apply at signpath.org with this public MIT repository. Builds must come from GitHub Actions, which this workflow does.
   After approval create a project with two artifact configurations named `files` (a folder of exe/dll/pyd) and `installer` (one exe), then set:
   secrets `SIGNPATH_API_TOKEN`, `SIGNPATH_ORGANIZATION_ID`; variables `SIGNPATH_PROJECT_SLUG`, `SIGNPATH_POLICY_SLUG`.
   The certificate is issued to "SignPath Foundation" as publisher.
2. **Azure Trusted Signing** (low monthly fee, check Microsoft's current eligibility rules for your country and entity type).
   Secrets `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`; variables `AZURE_TS_ENDPOINT`, `AZURE_TS_ACCOUNT`, `AZURE_TS_PROFILE`.
3. **Any exportable .pfx certificate** (OV or EV from Certum, Sectigo, DigiCert and others; Certum sells an open source certificate to individuals).
   Secrets `WIN_CERT_PFX_BASE64` (`base64 -w0 cert.pfx`) and `WIN_CERT_PASSWORD`. Certificates kept only on a hardware token or a cloud HSM cannot be exported and need option 1 or 2.

Every exe, dll and pyd in the app folder is signed first, then the installer. The job log ends with a signature report.

SmartScreen reputation builds per certificate over downloads; a new certificate may still show a warning for the first releases.

## macOS (Gatekeeper)

Apple Developer Program membership gives a "Developer ID Application" and "Developer ID Installer" certificate.
Secrets: `MAC_CERT_P12_BASE64` (both certificates exported into one .p12), `MAC_CERT_PASSWORD`, `MAC_IDENTITY`, `MAC_INSTALLER_IDENTITY`, and for notarization `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` (app specific password).
With them the app, dmg and pkg are signed with the hardened runtime, notarized and stapled, so they open with no prompt.

## Linux

`GPG_PRIVATE_KEY` and `GPG_PASSPHRASE` add a detached `.asc` to every file. Publish the public key in the README so users can run `gpg --verify`.

## Antivirus false positives

1. Set `VIRUSTOTAL_API_KEY` (free account). Each release is uploaded and the report links are added to the release notes.
2. If an engine flags a release, submit the file as a false positive:
   Microsoft Defender at microsoft.com/wdsi/filesubmission (choose "Software developer"), and the vendor portals of the other engines listed by VirusTotal.
   Signed files are cleared much faster and later versions inherit the reputation.
3. Never re-pack releases with UPX or similar tools.
