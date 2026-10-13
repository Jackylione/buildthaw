import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
CLI = PROJECT / "buildthaw.py"
TSC = PROJECT / ".tools/typescript-native/package/lib/tsc"


class CliTests(unittest.TestCase):
    def setUp(self):
        temporary = PROJECT / ".test-tmp"
        temporary.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary)
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def cache(self, name="tsconfig.tsbuildinfo", content=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(content if content is not None else {
            "version": "7.0.2", "fileNames": ["./index.ts"],
            "fileInfos": ["example-version-hash"], "root": [1],
            "options": {"incremental": True},
        }), encoding="utf-8")
        return path

    def run_cli(self, *arguments, root=None, timeout=15):
        return subprocess.run(
            [sys.executable, "-B", str(CLI), str(root or self.root), *arguments],
            cwd=PROJECT, text=True, capture_output=True, timeout=timeout,
        )

    def test_preview_lists_cache_without_changing_any_file(self):
        cache = self.cache(".cache/web.tsbuildinfo")
        source = self.root / "index.ts"
        source.write_text("export const answer = 42;\n")
        before = {p: p.read_bytes() for p in (cache, source)}

        result = self.run_cli()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('.cache/web.tsbuildinfo', result.stdout)
        self.assertIn('7.0.2', result.stdout)
        self.assertIn('1 cache(s); preview only', result.stdout)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_apply_removes_only_caches_and_is_repeatable(self):
        caches = [self.cache(), self.cache("packages/web/dist/web.tsbuildinfo")]
        outputs = {}
        for name in ("index.ts", "dist/index.js", "dist/index.d.ts", "dist/index.js.map"):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"keep these exact bytes\n")
            outputs[path] = path.read_bytes()

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Removed 2 cache(s)", result.stdout)
        self.assertTrue(all(not path.exists() for path in caches))
        self.assertEqual(outputs, {p: p.read_bytes() for p in outputs})
        again = self.run_cli("--apply")
        self.assertEqual(again.returncode, 0, again.stderr)
        self.assertIn("Removed 0 cache(s)", again.stdout)

    def test_discovery_skips_dependency_vcs_and_virtualenv_directories(self):
        kept = [self.cache(f"{directory}/internal.tsbuildinfo") for directory in (
            "node_modules", ".git", ".hg", ".svn", ".venv", "venv", "__pycache__",
            "packages/web/node_modules",
        )]
        selected = self.cache(".cache/app.tsbuildinfo")

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(selected.exists())
        self.assertTrue(all(path.exists() for path in kept))
        self.assertIn("Removed 1 cache(s)", result.stdout)

    def test_missing_or_non_directory_root_is_an_error(self):
        file = self.root / "ordinary-file"
        file.write_text("not a directory")
        for root in (self.root / "missing", file):
            with self.subTest(root=root.name):
                result = self.run_cli("--apply", root=root)
                self.assertEqual(result.returncode, 2)
                self.assertIn("root must be an existing directory", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("Removed", result.stdout)

    def test_malformed_cache_aborts_whole_preflight_without_deleting(self):
        good = self.cache("a-good.tsbuildinfo")
        bad = self.root / "z-broken.tsbuildinfo"
        for payload in (b'{"version":', b'\xff\xfe\x00'):
            with self.subTest(payload=payload):
                bad.write_bytes(payload)
                result = self.run_cli("--apply")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("z-broken.tsbuildinfo", result.stderr)
                self.assertIn("invalid UTF-8 JSON", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertTrue(good.exists())
                self.assertEqual(bad.read_bytes(), payload)

    @unittest.skipIf(not hasattr(os, "geteuid") or os.geteuid() == 0, "requires POSIX permissions and a non-root user")
    def test_unreadable_tree_or_cache_aborts_preflight(self):
        good = self.cache("a-good.tsbuildinfo")
        hidden = self.cache("restricted/hidden.tsbuildinfo")
        hidden.parent.chmod(0o000)
        self.addCleanup(hidden.parent.chmod, 0o700)

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("restricted", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertTrue(good.exists())
        hidden.parent.chmod(0o700)
        hidden.chmod(0o000)
        self.addCleanup(hidden.chmod, 0o600)
        file_result = self.run_cli("--apply")
        self.assertEqual(file_result.returncode, 2, file_result.stderr)
        self.assertIn("hidden.tsbuildinfo", file_result.stderr)
        self.assertTrue(good.exists())

    def test_json_that_is_not_recognized_build_info_is_never_deleted(self):
        good = self.cache("a-good.tsbuildinfo")
        for content in (
            {}, [], None, {"version": "7.0.2"},
            {"version": "not-typescript", "fileNames": [], "fileInfos": []},
            {"version": "7.0.2", "fileNames": "index.ts", "fileInfos": []},
            {"version": "7.0.2", "fileNames": ["index.ts"], "fileInfos": []},
            {"version": "7.0.2", "fileNames": ["index.ts"], "fileInfos": [{}]},
        ):
            with self.subTest(content=content):
                bad = self.root / "z-unrecognized.tsbuildinfo"
                bad.write_text(json.dumps(content))
                result = self.run_cli("--apply")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("unrecognized TypeScript build info", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertTrue(good.exists())
                self.assertTrue(bad.exists())

    @unittest.skipUnless(TSC.is_file(), "optional official TypeScript 7.0.2 compiler is not installed")
    def test_native_compiler_caches_reset_without_touching_outputs(self):
        for mode, options in (
            ("incremental", {"incremental": True}),
            ("composite", {"composite": True}),
            ("build", {}),
        ):
            with self.subTest(mode=mode):
                root = self.root / mode
                root.mkdir()
                (root / "index.ts").write_text("export const answer: number = 42;\n")
                (root / "tsconfig.json").write_text(json.dumps({
                    "compilerOptions": {"outDir": "dist", **options}, "files": ["index.ts"],
                }))
                command = [str(TSC), "-b" if mode == "build" else "-p", "tsconfig.json"]
                first = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                caches = list(root.rglob("*.tsbuildinfo"))
                self.assertEqual(len(caches), 1)
                outputs = {p: (p.read_bytes(), p.stat().st_mtime_ns)
                           for p in root.rglob("*") if p.is_file() and p not in caches}

                result = self.run_cli("--apply", root=root)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(all(not p.exists() for p in caches))
                self.assertEqual(outputs, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in outputs})
                again = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
                self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
                self.assertTrue(all(p.is_file() for p in caches))

    def test_discovery_does_not_follow_or_remove_symbolic_links(self):
        root = self.root / "project"
        root.mkdir()
        target = self.cache("outside/target.tsbuildinfo")
        (root / "linked.tsbuildinfo").symlink_to(target)
        (root / "dangling.tsbuildinfo").symlink_to(self.root / "missing")
        (root / "linked-directory").symlink_to(target.parent, target_is_directory=True)

        result = self.run_cli("--apply", root=root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Removed 0 cache(s)", result.stdout)
        self.assertTrue(target.exists())
        self.assertTrue((root / "linked.tsbuildinfo").is_symlink())
        self.assertTrue((root / "dangling.tsbuildinfo").is_symlink())
        link_root = self.root / "linked-root"
        link_root.symlink_to(root, target_is_directory=True)
        rejected = self.run_cli("--apply", root=link_root)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("symbolic link", rejected.stderr)

    def test_explicit_cache_paths_select_only_named_files_and_deduplicate(self):
        first = self.cache("node_modules/vitest/dist/tsconfig.tmp.tsbuildinfo")
        custom = self.cache("custom build cache")
        untouched = self.cache("unrelated.tsbuildinfo")

        result = self.run_cli("--apply", "--cache", str(first), "--cache", "custom build cache",
                              "--cache", "./custom build cache")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Removed 2 cache(s)", result.stdout)
        self.assertFalse(first.exists())
        self.assertFalse(custom.exists())
        self.assertTrue(untouched.exists())

    def test_explicit_paths_cannot_escape_root_or_follow_links(self):
        outside = self.cache("outside.tsbuildinfo")
        root = self.root / "project"
        root.mkdir()
        good = root / "good.tsbuildinfo"
        good.write_bytes(outside.read_bytes())
        (root / "link.tsbuildinfo").symlink_to(outside)
        (root / "linked-dir").symlink_to(self.root, target_is_directory=True)
        for target in (str(outside), "../outside.tsbuildinfo", "link.tsbuildinfo",
                       "linked-dir/outside.tsbuildinfo"):
            with self.subTest(target=target):
                result = self.run_cli("--apply", "--cache", "good.tsbuildinfo", "--cache", target, root=root)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("must stay inside root without symbolic links or '..'", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertTrue(good.exists())
                self.assertTrue(outside.exists())
                self.assertTrue((root / "link.tsbuildinfo").is_symlink())

    def test_missing_and_nonregular_explicit_caches_fail_without_deleting(self):
        good = self.cache("a-good.tsbuildinfo")
        directory = self.root / "directory.tsbuildinfo"
        directory.mkdir()
        for target in ("missing.tsbuildinfo", directory.name):
            with self.subTest(target=target):
                result = self.run_cli("--apply", "--cache", good.name, "--cache", target)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(target, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertTrue(good.exists())


    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX named pipes")
    def test_named_pipe_is_refused_without_hanging(self):
        good = self.cache("a-good.tsbuildinfo")
        pipe = self.root / "z-pipe.tsbuildinfo"
        os.mkfifo(pipe)

        result = self.run_cli("--apply", timeout=2)

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("not a regular file", result.stderr)
        self.assertTrue(good.exists())
        self.assertTrue(pipe.exists())


    @unittest.skipIf(not hasattr(os, "geteuid") or os.geteuid() == 0, "requires POSIX permissions and a non-root user")
    def test_delete_failure_reports_partial_progress_and_preserves_remaining_cache(self):
        first = self.cache("a-first.tsbuildinfo")
        blocked = self.cache("z-readonly/blocked.tsbuildinfo")
        blocked.parent.chmod(0o555)
        self.addCleanup(blocked.parent.chmod, 0o700)

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('REMOVED "a-first.tsbuildinfo"', result.stdout)
        self.assertIn("1 cache(s) removed before failure", result.stderr)
        self.assertIn("z-readonly/blocked.tsbuildinfo", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(first.exists())
        self.assertTrue(blocked.exists())


    def test_ambiguous_nonstandard_or_excessively_nested_json_is_refused(self):
        good = self.cache("a-good.tsbuildinfo")
        bad = self.root / "z-bad.tsbuildinfo"
        for payload in (
            '{"version":"6.0.3","version":"7.0.2","root":[]}',
            '{"version":"7.0.2","root":[],"extra":NaN}',
            '{"version":"7.0.2","root":[],"extra":' + '[' * 1500 + '0' + ']' * 1500 + '}',
        ):
            with self.subTest(payload=payload[:65]):
                bad.write_text(payload)
                result = self.run_cli("--apply")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("invalid UTF-8 JSON", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertTrue(good.exists())
                self.assertEqual(bad.read_text(), payload)


    def test_oversized_cache_is_refused_before_deletion(self):
        good = self.cache("a-good.tsbuildinfo")
        huge = self.root / "z-huge.tsbuildinfo"
        with huge.open("wb") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)

        result = self.run_cli("--apply")

        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("exceeds 64 MiB", result.stderr)
        self.assertTrue(good.exists())
        self.assertEqual(huge.stat().st_size, 67108865)


if __name__ == "__main__":
    unittest.main()
