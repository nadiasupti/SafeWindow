"""Give a person the government role (or take it away). The only way to create a government account.

There is no public government sign-up. The person first creates an ordinary account in the app (Account page), then
a project administrator runs this script ON THEIR OWN COMPUTER, where the Firebase Admin key is:

    $env:GOOGLE_APPLICATION_CREDENTIALS="E:\\keys\\safewindow-admin.json"
    python scripts/provision_government.py someone@example.org            # grant
    python scripts/provision_government.py someone@example.org --revoke    # take away
    python scripts/provision_government.py --list                          # who has it

It sets the custom claim role=gov, which firestore.rules checks on the server side. The person must sign out and
in again (or wait up to an hour) before the app shows the government desk. The Admin key never goes in the repository.
"""
from __future__ import annotations

import argparse
import os
import sys

ROLE = "gov"


def claims_after(existing: dict | None, grant: bool) -> dict:
    """The claims a user should have after granting or revoking: other claims are kept."""
    claims = dict(existing or {})
    if grant:
        claims["role"] = ROLE
    else:
        claims.pop("role", None)
    return claims


def _admin():
    import firebase_admin
    from firebase_admin import auth

    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    return auth


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email", nargs="?", help="the person's account email")
    parser.add_argument("--revoke", action="store_true", help="remove the government role")
    parser.add_argument("--list", action="store_true", help="list accounts that have the government role")
    args = parser.parse_args(argv)

    key = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key or not os.path.isfile(key):
        print("Set GOOGLE_APPLICATION_CREDENTIALS to the Firebase Admin key file (kept outside the repository).", file=sys.stderr)
        return 2
    auth = _admin()

    if args.list:
        found = [u for u in auth.list_users().iterate_all() if (u.custom_claims or {}).get("role") == ROLE]
        for u in found:
            print(u.email or u.uid)
        print(f"{len(found)} government account(s)")
        return 0

    if not args.email:
        parser.error("give an email, or use --list")
    try:
        user = auth.get_user_by_email(args.email)
    except auth.UserNotFoundError:
        print(f"No account for {args.email}. Ask them to create one in the app first.", file=sys.stderr)
        return 1
    auth.set_custom_user_claims(user.uid, claims_after(user.custom_claims, grant=not args.revoke))
    auth.revoke_refresh_tokens(user.uid)          # old sessions stop working: the person signs in again
    print(("Removed the government role from " if args.revoke else "Government role granted to ") + args.email)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
