import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from officialrules import Judge

from invoice_examples import cli


@pytest.fixture(scope="session")
def judge():
    return Judge()


@pytest.fixture
def run(capsys):
    def _run(*args):
        out = io.StringIO()
        try:
            code = cli.main([str(a) for a in args], out=out)
        except SystemExit as e:
            code = e.code
        captured = capsys.readouterr()
        return code, out.getvalue() + captured.out, captured.err

    return _run
