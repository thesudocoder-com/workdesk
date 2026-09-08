from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from Application.Authentication.Security import hash_password
from Application.Users.Models import UserRole
from Application.Users.Repository import UserRepository, initialize_database, session_scope
from Application.Users.Schemas import UserCreate
from Application.Users.Service import UserService
from Application.Finance.Migration import migrate_legacy_finance


ROLE_ALIASES = {
    "developer": UserRole.DEVELOPER,
    "outreach": UserRole.OUTREACH_MANAGER,
    "outreach-manager": UserRole.OUTREACH_MANAGER,
    "member": UserRole.TEAM_MEMBER,
    "team-member": UserRole.TEAM_MEMBER,
}


def role_value(value: str) -> UserRole:
    role = ROLE_ALIASES.get(value.strip().lower())
    if not role:
        raise argparse.ArgumentTypeError("choose developer, outreach-manager, or team-member")
    return role


def password_value(provided: str | None) -> str:
    password = provided or os.getenv("WORKDESK_CLI_PASSWORD")
    if password:
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters.")
        return password
    first = getpass.getpass("Temporary password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("Passwords do not match.")
    if len(first) < 10:
        raise ValueError("Password must contain at least 10 characters.")
    return first


def add_user(args: argparse.Namespace) -> None:
    password = password_value(args.password)
    user = UserService().create_user(
        UserCreate(name=args.name, email=args.email, role=args.role, password=password, password_confirmation=password)
    )
    print(f"Created {user.name} <{user.email}> as {user.role}.")


def list_users(_: argparse.Namespace) -> None:
    with session_scope() as session:
        users = UserRepository().list(session)
        if not users:
            print("No users found.")
            return
        width = max(4, *(len(user.name) for user in users))
        print(f"{'NAME':<{width}}  {'EMAIL':<32}  {'ROLE':<18}  STATUS")
        for user in users:
            status = "active" if user.is_active else "inactive"
            print(f"{user.name:<{width}}  {user.email:<32}  {user.role:<18}  {status}")


def set_user_status(args: argparse.Namespace) -> None:
    repository = UserRepository()
    with session_scope() as session:
        user = repository.get_by_email(session, args.email)
        if not user:
            raise ValueError(f"No user found for {args.email}.")
        active = args.action == "activate"
        if user.role == UserRole.DEVELOPER.value and not active:
            active_developers = repository.count_active_developers(session)
            if active_developers <= 1:
                raise ValueError("WorkDesk must always have at least one active Developer.")
        user.is_active = active
        print(f"{user.email} is now {'active' if active else 'inactive'}.")


def reset_password(args: argparse.Namespace) -> None:
    password = password_value(args.password)
    with session_scope() as session:
        user = UserRepository().get_by_email(session, args.email)
        if not user:
            raise ValueError(f"No user found for {args.email}.")
        user.password_hash = hash_password(password)
        user.must_change_password = True
        user.session_version += 1
        print(f"Password reset for {user.email}.")


def migrate_finance(args: argparse.Namespace) -> None:
    with session_scope() as session:
        report = migrate_legacy_finance(session, apply=args.apply)
        print(json.dumps({"mode": "apply" if args.apply else "dry-run", **report.to_dict()}, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workdesk", description="WorkDesk administration CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    users = commands.add_parser("users", help="Manage user accounts")
    actions = users.add_subparsers(dest="action", required=True)

    add = actions.add_parser("add", help="Create a user")
    add.add_argument("--name", required=True)
    add.add_argument("--email", required=True)
    add.add_argument("--role", type=role_value, default=UserRole.TEAM_MEMBER)
    add.add_argument("--password", help="Prefer the interactive prompt or WORKDESK_CLI_PASSWORD")
    add.set_defaults(handler=add_user)

    listing = actions.add_parser("list", help="List user accounts")
    listing.set_defaults(handler=list_users)

    for action in ("activate", "deactivate"):
        status = actions.add_parser(action, help=f"{action.title()} a user")
        status.add_argument("--email", required=True)
        status.set_defaults(handler=set_user_status)

    reset = actions.add_parser("reset-password", help="Set a new password")
    reset.add_argument("--email", required=True)
    reset.add_argument("--password", help="Prefer the interactive prompt or WORKDESK_CLI_PASSWORD")
    reset.set_defaults(handler=reset_password)

    finance = commands.add_parser("finance-migrate", help="Preview or apply the idempotent legacy finance migration")
    finance.add_argument("--apply", action="store_true", help="Create normalized records (default is dry-run)")
    finance.set_defaults(handler=migrate_finance)
    return parser


def main() -> None:
    initialize_database()
    args = build_parser().parse_args()
    try:
        args.handler(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
