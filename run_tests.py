"""Run all project checks and retain their actual results."""
import io
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
report = stream.getvalue()
(ROOT / 'docs' / 'test_results.txt').write_text(report, encoding='utf-8')
print(report)
sys.exit(0 if result.wasSuccessful() else 1)
