# Misaka

Claude Code Desktop GUI Client, built with Python + Flet.

## Requirements

- Python 3.10+
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) or bundled via SDK
- Anthropic API key or `ANTHROPIC_API_KEY` environment variable

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run the application
python -m misaka.main

# Or via entry point
misaka
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check misaka/

# Type check
mypy misaka/
```

## Architecture

See [docs/plans/2026-02-23-architecture-design.md](docs/plans/2026-02-23-architecture-design.md)
for the full architecture design document.

## License

MIT
