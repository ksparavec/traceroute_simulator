# Repository Guidelines

## Project Structure & Module Organization
- `src/`: Python package `tsim` (core, analyzers, executors, simulators, utils, shell, scripts).
- `tests/`: Pytest suite (unit/integration); namespace/network tests live here (see `README_NAMESPACE_TESTS.md`).
- `docs/`: Documentation for users/admins; `web/` and `wsgi/` contain the optional web UI.
- `ansible/`: Playbooks and helpers used for fact collection and system setup.
- Root: `Makefile`, `pyproject.toml`, `traceroute_simulator.yaml` (runtime config), `requirements.txt`.

## Build, Test, and Development Commands
- `make check-deps`: Verify Python and system dependencies.
- `pytest -q` or `make test`: Run tests (quick local loop). Coverage: `pytest --cov=tsim -q`.
- `make package`: Build wheel/sdist into `dist/`.
- Install locally: `make install-package USER=1` or `make install-pipx`.
- Run CLI: `make tsim ARGS='-s 10.1.1.1 -d 10.2.1.1'`.
- Network namespaces: `sudo -E make netsetup` / `sudo -E make netclean` (required for ns-based tests/tools).

## Coding Style & Naming Conventions
- Python ≥3.6; follow PEP 8. Indentation: 4 spaces; modules lowercase; `snake_case` for functions/vars; `PascalCase` for classes.
- Lint with `flake8`: `flake8 src tests` (fix issues before opening PRs).
- Prefer type hints and concise docstrings for public functions and CLI entry-points.

## Testing Guidelines
- Framework: `pytest` (+ `pytest-cov`). Place tests under `tests/` using `test_*.py` naming.
- Fast unit tests should not require sudo or network namespaces.
- Namespace/integration flows: use `make test-namespace` or targeted make test targets; many require `sudo -E` and prior `make netsetup`.
- Aim to keep/add coverage for changed code paths; include tests with new features/bugfixes.

## Commit & Pull Request Guidelines
- Commit style: Conventional prefixes used in history (e.g., `feat:`, `fix:`, `refactor:`, `docs:`). Keep subject ≤72 chars; explain rationale and impact in body.
- PRs must include: clear description, linked issues, test updates, and docs changes when applicable. Add CLI examples (`make … ARGS='…'`) and screenshots for web/UI changes.

## Security & Configuration Tips
- Some operations require elevated privileges (`sudo -E`), especially namespace setup and service tests. Avoid running on production hosts.
- Configure via `traceroute_simulator.yaml`. For facts, set `TRACEROUTE_SIMULATOR_FACTS` if using custom directories.
