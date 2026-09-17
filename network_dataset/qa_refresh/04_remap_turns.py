"""Create a staging turn class against the freshly copied QA edges."""

from _shared import load_and_validate_core_scripts


def main():
    _, turns, _ = load_and_validate_core_scripts()
    turns.main()


if __name__ == "__main__":
    main()

