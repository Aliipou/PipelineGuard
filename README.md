<div align="center">

[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

# PipelineGuard

**CI/CD pipeline security guard with automated code quality gates, vulnerability scanning, and deployment guardrails.**

</div>

## The Problem

CI/CD pipelines are trusted too much. Code with critical vulnerabilities, hardcoded secrets, and failing tests gets deployed because no one put a hard stop in the pipeline. PipelineGuard is that hard stop.

## What It Checks

**Secrets Detection**
Scans every commit for API keys, tokens, and credentials before they reach the repository. Patterns cover 120+ secret types across all major cloud providers and SaaS platforms.

**Dependency Vulnerabilities**
Cross-references all dependencies against the GitHub Advisory Database and OSV. Blocks deployments with known Critical or High severity CVEs.

**Code Quality Gates**
Configurable thresholds for complexity, coverage, and duplication. Fails the build if the codebase falls below your defined standards.

**Deployment Guardrails**
Pre-deployment checks: environment variable validation, infrastructure diff review, rollback plan verification.

## Quick Start

```yaml
# .github/workflows/security.yml
name: PipelineGuard

on: [push, pull_request]

jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Aliipou/PipelineGuard@main
        with:
          fail-on-secrets: true
          fail-on-cve-severity: high
          coverage-threshold: 80
```

## Configuration

```yaml
# .pipelineguard.yml
secrets:
  enabled: true
  fail_on_detection: true
  allowlist: []

vulnerabilities:
  enabled: true
  block_severity: [critical, high]
  ignore_cves: []

quality:
  coverage_minimum: 80
  complexity_maximum: 10
  duplication_maximum: 5

deployment:
  require_rollback_plan: true
  validate_env_vars: true
```

## License

MIT
