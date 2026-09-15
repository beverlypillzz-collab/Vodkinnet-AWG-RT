"""
Creates an admin account. Run inside the panel container:

    docker compose exec panel python3 scripts/create_admin.py

Prompts for username and password interactively so the password never
appears in shell history or docker-compose logs.
"""

import asyncio
import getpass
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select  # noqa: E402

from src.core.security import hash_password  # noqa: E402
from src.db.models import Admin  # noqa: E402
from src.db.session import db_session_context  # noqa: E402


async def main() -> None:
    username = input("Username: ").strip()
    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Confirm password: ")

    if password != password_confirm:
        print("Passwords don't match.")
        sys.exit(1)

    if len(password) < 8:
        print("Password should be at least 8 characters.")
        sys.exit(1)

    async with db_session_context() as session:
        existing = await session.execute(select(Admin).where(Admin.username == username))
        if existing.scalar_one_or_none() is not None:
            print(f"Admin '{username}' already exists.")
            sys.exit(1)

        admin = Admin(username=username, password_hash=hash_password(password))
        session.add(admin)
        await session.commit()

    print(f"Admin '{username}' created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
