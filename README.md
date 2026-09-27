# Shared Household Chores

## Run locally

1. Install dependencies:

       uv sync

2. Create the local database:

       uv run python manage.py migrate

3. Start the development server:

       uv run python manage.py runserver 127.0.0.1:8765

4. Run the test suite:

       uv run python manage.py test
