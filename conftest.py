"""Pytest bootstrap.

Config resolution is env-first and works with no Django at all; Django is
configured here only so the ``STAPEL_VAULT`` settings-override path (and
``override_settings``) can be exercised. No apps, no database.
"""


def pytest_configure(config):
    from django.conf import settings

    if not settings.configured:
        settings.configure(
            DEBUG=False,
            INSTALLED_APPS=[],
            DATABASES={},
            USE_TZ=True,
        )
        import django

        django.setup()
