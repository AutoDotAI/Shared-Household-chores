# Shared Household Chores

## Run locally

1. Install dependencies (Python 3.12 or newer):

       uv sync

2. (Optional) Configure email delivery. With `EMAIL_HOST` unset, Django prints sign-in and invitation emails to the console. For SMTP, set these environment variables before starting the server:

       EMAIL_HOST=smtp.example.com
       EMAIL_PORT=587
       EMAIL_HOST_USER=your-smtp-username
       EMAIL_HOST_PASSWORD=your-smtp-password
       EMAIL_USE_TLS=true
       DEFAULT_FROM_EMAIL=chores@example.com

   `EMAIL_HOST` selects Django's SMTP backend. `EMAIL_PORT` defaults to `587`, credentials default to empty strings, and `EMAIL_USE_TLS` defaults to `false`. `DEFAULT_FROM_EMAIL` defaults to `webmaster@localhost`. Keep credentials in your local environment or secret manager; do not commit them.

3. Create the local database:

       uv run python manage.py migrate

4. Start the development server:

       uv run python manage.py runserver 127.0.0.1:8765

5. Run the test suite:

       uv run python manage.py test

To run focused tests, use `uv run python manage.py test core.tests` or `uv run python manage.py test core.tests.HomePageTests.test_home_page_loads`.

## Work tracking

Tasks are tracked as [GitHub issues](https://github.com/AutoDotAI/Shared-Household-chores/issues) and handled one at a time. See the [backlog index](_docs/backlog.md) and [work process](_docs/process.md).
