"""Generate an administrator hash without receiving a password in argv or chat."""

from getpass import getpass

from argon2 import PasswordHasher

if __name__ == "__main__":
    password = getpass("Administrator password (at least 12 characters): ")
    if len(password) < 12 or len(password) > 256:
        raise SystemExit("Password must contain 12–256 characters")
    if password != getpass("Confirm password: "):
        raise SystemExit("Passwords differ")
    print(PasswordHasher().hash(password))
