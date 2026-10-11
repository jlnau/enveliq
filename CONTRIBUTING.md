# Helping with Enveliq

Thank you for wanting to help. Enveliq is a small, calm project, and good reports are as valuable as code.

## Ways to help

- **Something is not working.** [Open an issue](https://github.com/jlnau/enveliq/issues/new/choose) and pick "Something is not working". The form asks for what we need.
- **You are stuck installing it.** Pick "I am stuck installing it". Where the guides let you down is the most useful thing we can learn.
- **A page or a word is confusing.** Pick "A guide is confusing or wrong".
- **You have an idea.** Pick "I have an idea". Describe what you are trying to do, and we can work out the best way together.
- **A security problem.** Do not use a public issue. Use the [private form](https://github.com/jlnau/enveliq/security/advisories/new). See [SECURITY.md](SECURITY.md).

Please never paste real email, passwords, setup codes, keys or tokens into an issue, a screenshot or a pull request.

## What Enveliq will not change

These promises keep people's mail safe, so a change that breaks one will not be accepted:

- Raw email bodies and attachments are never stored. Only encrypted summaries and results are kept.
- One person's data is never visible to another person. The server decides who may read, never the page.
- Secrets are write-only from the browser: never sent back and never logged.
- Email text is untrusted. The AI gets no tools, treats email as data, and never decides for you.
- The website and the app load nothing from other sites.

## Sending a change

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach before you spend time on it.
2. Make your change on a branch (`feat/...`, `fix/...` or `docs/...`) and open a pull request. Keep it to one topic. The template lists what we look for.
3. Add or update tests (`tests/` for the backend, `scripts/check_*.mjs` for pages). The checks run automatically on your pull request.
4. Use plain, kind wording for anything a normal user sees. Test data must be made up: use `example.com`, `.invalid` or `.example`, and private addresses like `192.168.1.x`.

To run the checks yourself, see "For developers" in the [README](README.md) and the files in [`docs/`](docs/README.md).
