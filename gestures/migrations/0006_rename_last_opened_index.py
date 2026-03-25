"""Fix index naming for SQLite identifier length.

On some SQLite builds, `ALTER INDEX ... RENAME TO ...` may not be supported.
Instead we read the CREATE INDEX SQL from sqlite_master, drop the old index,
and recreate it using the shorter name.
"""

from django.db import migrations


OLD_NAME = "gestures_pr_user_id_last_opened_idx"
NEW_NAME = "gest_pr_usr_last_open_idx"


def rename_index_if_needed(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "sqlite":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=%s",
            [OLD_NAME],
        )
        if not cursor.fetchone():
            return

        # Get the index creation SQL. If it's missing, we can't safely recreate.
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=%s",
            [OLD_NAME],
        )
        row = cursor.fetchone()
        create_sql = row[0] if row else None

        # Drop old index first.
        cursor.execute(f'DROP INDEX IF EXISTS "{OLD_NAME}"')

        if not create_sql:
            return

        # Avoid duplicate creation if the short index already exists.
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=%s",
            [NEW_NAME],
        )
        if cursor.fetchone():
            return

        # Recreate with the new (short) index name.
        # The index name appears inside the CREATE INDEX statement, so a simple
        # string replacement is sufficient here.
        create_sql_new = create_sql.replace(OLD_NAME, NEW_NAME)
        cursor.execute(create_sql_new)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("gestures", "0005_presentationasset_last_opened_at"),
    ]

    operations = [
        migrations.RunPython(rename_index_if_needed, noop_reverse),
    ]
