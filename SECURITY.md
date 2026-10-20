# Security Policy

Crypton handles file storage and network communication. Security reports are welcome, and responsible disclosure helps protect users.

## Important limitations

Read the project's README and documentation before evaluating or deploying Crypton. Do not assume that encrypted network communication means end-to-end encryption, that the server cannot access file contents, or that a custom protocol has been independently audited.

The project's documented behavior and limitations may change. Review the current implementation and documentation; do not treat this policy as a security guarantee or certification.

## Reporting a vulnerability

**Please do not report suspected vulnerabilities in public GitHub issues, discussions, pull requests, or public posts.** Public reports can expose users before a fix is available.

1. If private vulnerability reporting is enabled for this repository, use GitHub's **Report a vulnerability** feature on the repository's Security tab.
2. If private reporting is unavailable, contact the repository maintainer privately through a contact method listed on the maintainer's GitHub profile. Do not send exploit details through a public issue.

If you cannot find a private channel, you can ask publicly how to contact the maintainer, but do not include the suspected vulnerability, exploit steps, sensitive data, or proof of concept.

## What to include

Please share as much of the following as you can safely provide:

- A concise description of the suspected vulnerability and its potential impact.
- The affected version, commit, component, and environment, if known.
- Preconditions and a minimal reproduction or proof of concept, if safe to share privately.
- The threat assumptions required for the issue to occur.
- Any suggested mitigation, if you have one.

Please redact credentials, tokens, private keys, personal information, and real user files. Do not access, modify, or exfiltrate data that does not belong to you. Test only on systems and data you own or have explicit permission to test.

## What to expect

The maintainer will review the report and may ask for clarification. Please allow reasonable time for investigation and remediation. Response times and release timelines are not guaranteed.

Please coordinate public disclosure with the maintainer when possible. Do not assume a report is confirmed until it has been investigated.

## Scope

Reports involving authentication, authorization, confidentiality, integrity, unsafe file handling, protocol parsing, cryptographic design or implementation, secrets handling, and denial-of-service risks may be relevant.

Not every bug is a security vulnerability. General bugs and feature requests should be filed using the public issue templates, provided they do not reveal an exploitable security weakness.

## Safe harbor

Act in good faith, follow applicable laws, avoid privacy violations and service disruption, and stop testing if you encounter data that is not yours. This policy is not legal advice and does not grant permission to test systems you do not own or have authorization to assess.
