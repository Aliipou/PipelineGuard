# Contributing to PipelineGuard

## Setup

```bash
git clone https://github.com/Aliipou/PipelineGuard.git
cd PipelineGuard
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v --cov=pipelineguard
```

## Adding a New Secret Pattern

1. Add the pattern to `pipelineguard/patterns/secrets.py`
2. Include at least 3 test cases: true positive, false positive, edge case
3. Document the pattern source (e.g., official docs, known format)

## Commit Messages

`feat:`, `fix:`, `docs:`, `test:`, `chore:`
