
# Helping with Enveliq

Thank you for wanting to help make Enveliq better.

Enveliq is a free, open source, self hosted AI email assistant built around a simple idea: **email should take less of your time, not more of it.**

Whether you run Enveliq in a homelab, use local AI, care about privacy, or simply want a quieter inbox, your experience matters.

You do not need to be a developer to contribute. A useful bug report, an installation problem, a confusing instruction or a thoughtful suggestion can be just as valuable as code.

## Ways to help

Anyone with a GitHub account can report problems, suggest improvements and participate in discussions.

- **Something is not working.** [Open an issue](https://github.com/jlnau/enveliq/issues/new/choose) and select "Something is not working". Describe what happened, what you expected and how to reproduce it.
- **You are stuck installing it.** Select "I am stuck installing it". Whether you are using Docker, Proxmox, Unraid, a NAS or another platform, knowing where the instructions let you down helps improve the experience for everyone.
- **A page or a word is confusing.** Select "A guide is confusing or wrong". Clear documentation matters, especially for people who are new to self hosting.
- **You have an idea.** Select "I have an idea". Explain the problem you want to solve or the experience you want to improve. Suggestions around privacy, local AI, homelabs, accessibility and everyday email management are welcome.
- **You want to contribute code or documentation.** Developers and technical contributors are welcome to suggest fixes, improvements and documentation changes through pull requests.
- **You have found a security problem.** Please do not open a public issue. Use the [private security reporting form](https://github.com/jlnau/enveliq/security/advisories/new) and follow [SECURITY.md](SECURITY.md).

**Protect your privacy and everyone else's.** Never include real email content, passwords, setup codes, API keys, authentication tokens or other secrets in issues, screenshots, logs or pull requests.

When sharing examples, use invented names, messages and addresses.

## What Enveliq will not change

Privacy, security and control over personal information are fundamental to Enveliq.

These are architectural requirements, not optional features. Contributions that compromise them will not be accepted.

- **Your email remains with your provider.** Raw email bodies and attachments are processed temporarily when needed but are not retained as permanent application data. Enveliq stores encrypted summaries, metadata and structured results.

- **Your private information stays private.** Each person's data is protected by access controls enforced by the server, never trusted to the browser. Administrator access does not automatically grant permission to read another person's email.

- **Secrets remain protected.** Passwords, authentication tokens, provider credentials and AI API keys must never be returned to the browser after being saved or exposed in application logs. Sensitive information is protected using the encrypted vault.

- **AI never gains independent control of your email.** Email and attachment content must always be treated as untrusted data. AI processing must not provide access to system tools, secrets or independent permission to send, delete or modify messages. User configured automation rules operate separately under defined restrictions.

- **No advertising, tracking or unnecessary external resources.** Enveliq's browser interface loads its application resources locally without third party advertising, analytics or tracking scripts. Server connections to email providers, AI services, notification systems, authentication providers and other integrations must follow the application's security and privacy controls.

- **Self hosting must remain a genuine option.** Enveliq must not require an account with its developer, a paid subscription or a particular commercial AI provider. People must remain free to run the application on infrastructure they control and use compatible AI models on their own network.

Changes involving authentication, encryption, mailbox access, AI processing, external connections or persistent storage should be reviewed particularly carefully.

For the detailed security requirements, see [SECURITY.md](SECURITY.md). For information about what Enveliq stores and processes, see the [privacy documentation](docs/PRIVACY.md).

## Contributing to Enveliq

You do not need technical knowledge to help improve Enveliq.

There are two main ways to contribute: sharing your experience as a user or proposing changes to the project itself.

### Reporting problems and suggesting improvements

Anyone with a GitHub account can [open an issue](https://github.com/jlnau/enveliq/issues/new/choose).

Tell us what is not working, what could be better, or what you would like Enveliq to do.

You do not need to understand the technical side or know how to fix the problem yourself.

Feedback about installation, privacy, local AI, homelab setups, Home Assistant and everyday usability is particularly welcome.

A good report explains what happened, what you expected to happen and, if possible, how someone else can reproduce the problem.

### Contributing code or documentation

If you are comfortable working with GitHub and would like to contribute code, documentation or other improvements, you are welcome to submit a pull request.

You do not need special access to the Enveliq repository to propose changes.

1. **Discuss larger changes first.** [Open an issue](https://github.com/jlnau/enveliq/issues/new/choose) to explain your idea before spending significant time implementing it. Small fixes, such as correcting a typo, generally do not need prior discussion.

2. **Fork the repository.** Create your own copy of Enveliq using GitHub's Fork option. You can make changes in your own fork without modifying the original project.

3. **Create a branch.** Work on a separate branch in your fork. Use a descriptive name beginning with `feat/`, `fix/` or `docs/`, depending on the type of change.

4. **Make your changes.** Keep each contribution focused on one problem or improvement. Avoid changing unrelated functionality, configuration or documentation.

5. **Test your changes.** Run relevant tests where possible and check that existing functionality continues to work. If you cannot run a particular test, mention that in your pull request.

6. **Submit a pull request.** Open a pull request from your fork to the main Enveliq repository. Explain what you changed, why you changed it and how you tested it.

7. **Respond to feedback.** Changes may be requested during review. This is a normal part of collaborative development and helps protect the quality and security of the project.

Pull requests are reviewed before changes are accepted into Enveliq. Not every proposed change will necessarily be merged.

**Submitting a pull request does not give anyone permission to modify the original repository directly.** All proposed changes remain separate until reviewed and accepted by the project maintainer.

### Guidelines for contributions

A few principles help keep Enveliq safe, reliable and approachable.

- **Keep changes focused.** A pull request should address one issue or improvement wherever possible.
- **Preserve existing functionality.** Do not remove unrelated settings, configuration, user preferences, stored data or established behaviour.
- **Respect privacy and security.** Changes involving authentication, AI processing, mailbox operations, external connections or user information must preserve Enveliq's security principles.
- **Use invented test data.** Never include real personal information. Use domains such as `example.com`, `.invalid` or `.example`, and private network examples such as `192.168.1.x`.
- **Keep the interface understandable.** Use clear, friendly language that makes sense to someone who does not work in technology.
- **Include tests when appropriate.** Backend changes should include or update tests in `tests/`. Browser and interface checks belong in `scripts/`.
- **Explain your changes clearly.** A useful pull request describes the problem, the solution and any potential effects on existing behaviour.

## Running the checks

If you are contributing code, please run the relevant checks locally where possible before submitting your pull request.

Backend tests are located in `tests/`, while browser and interface checks are maintained in `scripts/`.

Automated checks also run through GitHub Actions when a pull request is opened.

For development setup, dependencies and testing commands, see the **For developers** section of the [README](README.md).

Additional technical guides are available in the [documentation index](docs/README.md).

If you cannot run a particular check locally, explain that in your pull request rather than leaving it unmentioned.

## A final note

Enveliq is intended to make technology feel quieter, simpler and more useful.

That applies to contributing as much as it does to using the application.

Small improvements are welcome. Clear explanations are appreciated. Thoughtful discussions matter.

Whether you are fixing a bug, improving documentation, suggesting a feature or simply pointing out something that could work better, your contribution is valuable.

You do not need to know everything about the project to make a difference.

**Thank you for helping make Enveliq better.**
