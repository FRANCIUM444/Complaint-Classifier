"""Trusted operator utility. Run only from a secured shell with database access."""
import argparse
from sqlalchemy import select
from backend.app.main import SessionLocal, User

def main():
    parser = argparse.ArgumentParser(description="Assign a CampusCare role to an existing account.")
    parser.add_argument("email")
    parser.add_argument("role", choices=["student", "staff", "admin", "moderator"])
    args = parser.parse_args()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if not user:
            raise SystemExit("No account found for that email.")
        user.role = args.role
        db.commit()
        print(f"Updated role for {user.email} to {user.role}")

if __name__ == "__main__":
    main()
