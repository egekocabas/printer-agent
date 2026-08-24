# Contributing

Thanks for helping improve `printer-agent`.

## Development setup

Python 3.12 or newer is required. The mock backend means contributors do not need printer hardware.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Run the complete local verification suite before opening a pull request:

```bash
ruff format --check .
ruff check .
mypy
pytest
```

Tests must remain hardware-free and deterministic. Add or update tests for observable behavior
changes, and keep public API or configuration changes reflected in `docs/` and `.env.example`.

## Commits and pull requests

Use [Conventional Commits](https://www.conventionalcommits.org/) for commit and pull request titles,
for example:

```text
feat: add printer capability discovery
fix: reconnect after a USB timeout
docs: clarify image preview behavior
```

Keep changes focused. Pull requests should explain the motivation and approach, list the checks
that were run, and call out compatibility or hardware implications. Avoid committing `.env`,
device-specific secrets, generated artifacts, or editor files.

By contributing, you agree that your contributions are licensed under the repository's MIT License.
