import contextlib
import importlib.util
import io
import runpy
from pathlib import Path
import unittest


class MainEntrypointSafetyTests(unittest.TestCase):
    def test_import_and_direct_entrypoint_do_not_emit_output(self):
        project_root = Path(__file__).resolve().parents[1]
        main_path = project_root / "main.py"
        spec = importlib.util.spec_from_file_location(
            "main_entrypoint_under_test",
            main_path,
        )
        module = importlib.util.module_from_spec(spec)
        captured = io.StringIO()

        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            spec.loader.exec_module(module)
            module.main()
            runpy.run_path(str(main_path), run_name="__main__")

        self.assertEqual(captured.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
