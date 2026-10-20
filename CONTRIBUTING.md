# Contributing to Crypton

Thanks for your interest in improving Crypton! Contributions of all kinds are welcome. You do not need to submit code—or understand the entire codebase—to help.

Useful contributions include security reviews, bug reports, cross-platform testing, documentation improvements, design discussions, tests, and code changes.

## Before you start

1. Read the project README and its documented security limitations.
2. Search existing issues and pull requests to avoid duplicates.
3. For a substantial change, open an issue first to discuss the approach.
4. Never include passwords, private keys, tokens, real user data, or sensitive logs in issues or pull requests.

## Ways to contribute

- **Report a bug:** Use the Bug report issue form and include reproducible steps.
- **Test on another system:** Share your operating system, environment, steps, and results using the Testing report form.
- **Review security:** Read `SECURITY.md` first. Report suspected vulnerabilities privately; do not post exploit details in a public issue.
- **Improve documentation:** Fix unclear setup steps, explain behavior, or add examples.
- **Suggest an improvement:** Use the Feature request form to describe the problem and the outcome you would like.
- **Contribute code:** Fix a bug, add tests, improve error handling, or make a focused improvement.

## Issues

Please provide enough context for someone else to understand or reproduce the problem. Include relevant environment details, expected and actual behavior, and sanitized logs where useful. If you are unsure whether something is worth reporting, it is fine to open an issue and ask.

Please be respectful and constructive. Questions, disagreement, and careful criticism are welcome.

## Pull requests

- Keep changes focused and explain the problem they solve.
- Link related issues where applicable.
- Describe what changed, why it changed, and how you tested it.
- Add or update tests when practical.
- Update documentation when behavior, configuration, or setup changes.
- Do not include unrelated formatting changes, generated files, credentials, private data, or build artifacts.
- Call out platform-specific behavior and any tests you could not run.
- Be candid about limitations and remaining work.

Before submitting, check that:
- [ ] The change is limited to the stated purpose.
- [ ] Tests or manual checks have been run where possible.
- [ ] Documentation is updated where needed.
- [ ] No secrets or sensitive data are included.
- [ ] The pull request explains the testing performed and known limitations.

If the project does not yet have automated tests or a documented build/test command for your change, say so rather than implying checks passed.

## Security contributions

Independent scrutiny is especially valuable for software involving storage, authentication, networking, and cryptography. Please distinguish confirmed findings from hypotheses, describe assumptions, and avoid claiming that a design is secure based only on a limited review.

**Do not disclose suspected vulnerabilities publicly.** Follow `SECURITY.md` for private reporting instructions. Do not access, modify, or download other people's data while testing.

## Review and merging

Submitting a pull request does not guarantee that it will be merged. The maintainer may ask questions, request changes, defer work, or close a contribution that does not fit the project's direction. Please be patient; review time may vary.

Thank you for helping make Crypton more reliable, understandable, and secure.
