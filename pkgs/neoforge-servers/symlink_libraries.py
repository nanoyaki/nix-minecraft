import argparse
import os
import re
from pathlib import Path


def resolve_symlinks(unix_args: Path):
    """
    Resolve references to paths in the Nix store so we don't have a bunch of
    extra cruft laying around
    """

    library_root = Path("libraries")
    with unix_args.open("r") as f:
        lines = f.readlines()
    with unix_args.open("w") as w:
        for line in lines:
            if line.startswith("-DlibraryDirectory="):
                print(f"-DlibraryDirectory={library_root.resolve()}", file=w)
                continue
            for maybe_path in re.split(r"([:=\s])libraries/", line.rstrip()):
                if (path := library_root / maybe_path).exists() and path.is_symlink():
                    path = Path(os.path.realpath(path))
                    # print(f"resolved path : {maybe_path} -> {path}", file=sys.stderr)
                    print(path, file=w, end="")
                else:
                    # print(f"not a path: {maybe_path}", file=sys.stderr)
                    print(maybe_path, file=w, end="")
            print(file=w)


def remove_symlinks():
    for root, dirs, files in Path(".").walk(top_down=False):
        for file in files:
            if (path := root / file).is_symlink():
                path.unlink()

        for dir in dirs:
            if not any((dir := root / dir).iterdir()):
                dir.rmdir()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("unix_args_path", type=str)
    args = parser.parse_args()

    resolve_symlinks(Path(args.unix_args_path))
    remove_symlinks()
