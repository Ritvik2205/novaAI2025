# Migrations

Use Alembic (configured via `alembic.ini`, not included) to manage schema. Suggested commands:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

At minimum run `alembic upgrade head` after cloning to create tables defined in `app.db`.
