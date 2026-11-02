"""Runtime requirements fail clearly before GUI or hardware libraries load."""

from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from core.runtime import require_python


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RuntimeVersionTests(unittest.TestCase):
    def test_accepts_python3912_and_newer_versions(self):
        for version in ((3, 9, 12), (3, 9, 13), (3, 10, 0), (3, 14, 2)):
            with self.subTest(version=version), patch("sys.version_info", version):
                require_python()

    def test_rejects_older_versions_with_migration_instructions(self):
        for version in ((3, 8, 20), (3, 9, 6), (3, 9, 11)):
            with self.subTest(version=version), patch("sys.version_info", version):
                with self.assertRaises(SystemExit) as result:
                    require_python()
                message = str(result.exception)
                self.assertIn("requires Python 3.9.12 or newer", message)
                self.assertIn("found Python " + ".".join(map(str, version)), message)
                self.assertIn(".venv", message)
                self.assertIn("setup.bat", message)
                self.assertIn("./setup.sh", message)

    def test_entrypoints_reject_wrong_python_before_loading_dependencies(self):
        for entrypoint in ("core/runtime.py", "main.py", "Historian/Historian.py"):
            for version in ((3, 8, 20), (3, 9, 11)):
                with self.subTest(entrypoint=entrypoint, version=version):
                    script = textwrap.dedent("""\
                        import builtins
                        import runpy
                        import sys

                        original_import = builtins.__import__
                        def blocked_import(name, *args, **kwargs):
                            if name.split('.')[0] in (
                                'tkinter', 'PIL', 'labjack', 'influxdb_client', 'flask'
                            ):
                                raise RuntimeError('Dependency imported before version check')
                            return original_import(name, *args, **kwargs)

                        builtins.__import__ = blocked_import
                        sys.version_info = {version!r}
                        runpy.run_path({entrypoint!r}, run_name='__main__')
                        """).format(version=version, entrypoint=entrypoint)
                    result = subprocess.run(
                        [sys.executable, "-c", script], cwd=PROJECT_ROOT,
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("requires Python 3.9.12 or newer", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
