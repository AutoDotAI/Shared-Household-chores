## Commands

- `uv sync` - install dependencies
- `uv run python manage.py test` - run the whole Django test suite
- `uv run python manage.py test core.tests` - run the tests in `core/tests.py`
- `uv run python manage.py test core.tests.HomePageTests.test_home_page_loads` - run one test

## Rules

- Dependencies are added in `pyproject.toml`. Do not add one without
  asking


## Documents

- [_docs/process.md](_docs/process.md) - how work is organized
- [_docs/plan.md](_docs/plan.md) - product scope and business rules
- [_docs/backlog.md](_docs/backlog.md) - index of the GitHub issues
