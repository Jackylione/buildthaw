"""Clear TypeScript build-info caches without deleting compiled outputs."""

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys


EXCLUDED = {"node_modules", ".git", ".hg", ".svn", ".venv", "venv", "__pycache__"}
MAX_BYTES = 64 * 1024 * 1024


def strict_json(text):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("nonstandard JSON number")

    data = json.loads(text, object_pairs_hook=unique_object, parse_constant=nonfinite)
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 64:
            raise ValueError("JSON nesting exceeds 64")
        if isinstance(value, dict):
            pending.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            pending.extend((child, depth + 1) for child in value)
    return data


def recognized(data):
    if not isinstance(data, dict):
        return False
    version = data.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.+-]+)?", version):
        return False
    if "fileNames" not in data and "fileInfos" not in data:
        roots = data.get("root")
        return isinstance(roots, list) and all(isinstance(name, str) and name for name in roots)
    names, infos = data.get("fileNames"), data.get("fileInfos")
    if not isinstance(names, list) or not isinstance(infos, list) or len(names) != len(infos):
        return False
    if not all(isinstance(name, str) and name for name in names):
        return False
    return all(
        (isinstance(info, str) and bool(info)) or
        (isinstance(info, dict) and isinstance(info.get("version"), str) and bool(info["version"]))
        for info in infos
    )


def discover(root):
    def unreadable(error):
        raise error

    for directory, directories, files in os.walk(root, onerror=unreadable):
        directories[:] = sorted(d for d in directories if d not in EXCLUDED and not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            if name.endswith(".tsbuildinfo"):
                path = Path(directory) / name
                if path.is_symlink():
                    print(f"SKIP {json.dumps(path.relative_to(root).as_posix())} (symbolic link)")
                else:
                    yield path


def inside_without_links(path, root):
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return False
    if ".." in parts:
        return False
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="project directory")
    parser.add_argument("--apply", action="store_true", help="remove caches after preflight")
    parser.add_argument("--cache", action="append", help="select only named caches (repeatable; paths relative to root)")
    args = parser.parse_args()
    root = Path(args.root)
    if root.is_symlink():
        print("ERROR: root must not be a symbolic link", file=sys.stderr)
        return 2
    if not root.is_dir():
        print("ERROR: root must be an existing directory", file=sys.stderr)
        return 2
    root = root.resolve()
    try:
        caches = sorted(set(root / name for name in args.cache)) if args.cache else sorted(discover(root))
    except OSError as error:
        print(f"ERROR {json.dumps(error.filename)}: {error.strerror}; nothing removed", file=sys.stderr)
        return 2
    for path in caches:
        if not inside_without_links(path, root):
            print(f"ERROR {json.dumps(str(path))}: cache must stay inside root without symbolic links or '..'; nothing removed", file=sys.stderr)
            return 2
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                print(f"ERROR {json.dumps(path.relative_to(root).as_posix())}: not a regular file; nothing removed", file=sys.stderr)
                return 2
            with path.open("rb") as stream:
                content = stream.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                print(f"ERROR {json.dumps(path.relative_to(root).as_posix())}: exceeds 64 MiB; nothing removed", file=sys.stderr)
                return 2
            data = strict_json(content.decode("utf-8"))
        except OSError as error:
            print(f"ERROR {json.dumps(path.relative_to(root).as_posix())}: {error.strerror}; nothing removed", file=sys.stderr)
            return 2
        except (ValueError, UnicodeError, RecursionError):
            print(f"ERROR {json.dumps(path.relative_to(root).as_posix())}: invalid UTF-8 JSON or nesting above 64; nothing removed", file=sys.stderr)
            return 2
        if not recognized(data):
            print(f"ERROR {json.dumps(path.relative_to(root).as_posix())}: unrecognized TypeScript build info; nothing removed", file=sys.stderr)
            return 2
        print(f'CACHE {json.dumps(path.relative_to(root).as_posix())} (TypeScript {data["version"]})')
    if args.apply:
        for removed, path in enumerate(caches):
            try:
                path.unlink()
            except OSError as error:
                print(f"ERROR {json.dumps(path.relative_to(root).as_posix())}: {error.strerror}; {removed} cache(s) removed before failure", file=sys.stderr)
                return 2
            print(f"REMOVED {json.dumps(path.relative_to(root).as_posix())}")
        print(f"Removed {len(caches)} cache(s). Run your usual typecheck/build again.")
    else:
        print(f"{len(caches)} cache(s); preview only. Use --apply to remove.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
