from .db import engine
from .migrations import run_migrations


def main() -> None:
    applied = run_migrations(engine)
    print(f"FlowForge database tables and migrations are ready ({', '.join(applied)}).")


if __name__ == "__main__":
    main()
