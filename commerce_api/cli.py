from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import update

from commerce_api.core.config import Settings
from commerce_api.db.models import User
from commerce_api.db.session import create_engine, create_session_factory


async def promote_platform_admin(email: str) -> None:
    settings = Settings()
    engine = create_engine(settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            result = await session.execute(
                update(User).where(User.email == email.strip().lower()).values(is_platform_admin=True)
            )
            if not result.rowcount:
                raise SystemExit("No registered user found for that email")
            await session.commit()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="commerce-api")
    subparsers = parser.add_subparsers(dest="command", required=True)
    promote = subparsers.add_parser("promote-platform-admin")
    promote.add_argument("email")
    args = parser.parse_args()
    if args.command == "promote-platform-admin":
        asyncio.run(promote_platform_admin(args.email))


if __name__ == "__main__":
    main()