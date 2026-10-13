"""
make_super_admin.py
CLI script to promote an existing user to the 'super_admin' role.

Usage:
    python scripts/make_super_admin.py --email user@example.com
"""
import sys
import os
import argparse
import asyncio

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.database import AsyncSessionLocal, engine
from app.models.user import User


async def promote_user(email: str) -> bool:
    normalized_email = email.strip().lower()
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.email == normalized_email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            print(f"[ERROR] User with email '{email}' not found.", file=sys.stderr)
            return False

        if user.role == "super_admin":
            print(f"[INFO] User '{user.email}' is already a super_admin.")
            return True

        old_role = user.role
        user.role = "super_admin"
        await session.commit()
        print(f"[SUCCESS] User '{user.email}' successfully promoted from '{old_role}' to 'super_admin'.")
        return True


def main():
    parser = argparse.ArgumentParser(description="Promote an existing user to super_admin.")
    parser.add_argument(
        "--email",
        required=True,
        help="Email address of the existing user to promote.",
    )
    args = parser.parse_args()

    success = asyncio.run(promote_user(args.email))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
