import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def scratch_outputs():
    """A throwaway folder under {outputs}, so macro paths can be tested for real. Returns (folder, macro form).

    The folder is made here with a name nothing else uses, and only that folder is removed afterwards.
    """
    from griptape_nodes.files.file import File

    try:
        outputs = Path(File("{outputs}").resolve())
        folder = outputs / f"zz_otio_test_{uuid.uuid4().hex[:8]}"
        folder.mkdir(parents=True)
    except Exception as e:
        pytest.skip(f"{{outputs}} cannot be used for a macro path test here: {e}")
    try:
        yield folder, f"{{outputs}}/{folder.name}"
    finally:
        shutil.rmtree(folder, ignore_errors=True)
