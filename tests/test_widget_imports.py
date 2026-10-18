import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("stamp_widget_imports", ROOT / "scripts" / "stamp_widget_imports.py")
assert spec and spec.loader
stamp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stamp)


def test_the_real_widgets_are_stamped():
    folders = stamp.widget_folders()
    assert folders
    for folder in folders:
        assert stamp.stale_files(folder) == [], f"run `make widget/stamp` for {folder.name}"


def copy_widget(tmp_path: Path) -> Path:
    target = tmp_path / "w"
    shutil.copytree(ROOT / "otio_nodes" / "widgets" / "TimelineEditor", target)
    return target


def test_every_relative_import_carries_the_same_hash(tmp_path: Path):
    folder = copy_widget(tmp_path)
    stamp.stamp_folder(folder)
    version = stamp.folder_hash(folder)
    found = 0
    for path in stamp.widget_files(folder):
        for match in stamp.IMPORT.finditer(path.read_text(encoding="utf-8")):
            found += 1
            assert match.group(3) == f"?v={version}"
    assert found > 5


def test_stamping_twice_changes_nothing(tmp_path: Path):
    folder = copy_widget(tmp_path)
    stamp.stamp_folder(folder)
    assert stamp.stamp_folder(folder) == []


def test_editing_any_file_makes_every_stamp_stale(tmp_path: Path):
    folder = copy_widget(tmp_path)
    stamp.stamp_folder(folder)
    assert stamp.stale_files(folder) == []
    ops = folder / "_ops.js"
    ops.write_text(ops.read_text(encoding="utf-8") + "\nexport const added = 1;\n", encoding="utf-8")
    stale = {p.name for p in stamp.stale_files(folder)}
    assert {"TimelineEditor.js", "_viewer.js"} <= stale
    stamp.stamp_folder(folder)
    assert stamp.stale_files(folder) == []


def test_imports_without_a_stamp_are_found_and_fixed(tmp_path: Path):
    folder = tmp_path / "w"
    folder.mkdir()
    (folder / "a.js").write_text("import { x } from './b.js';\nimport y from '../c.js?v=deadbeef';\n", encoding="utf-8")
    (folder / "b.js").write_text("export const x = 1;\n", encoding="utf-8")
    assert [p.name for p in stamp.stale_files(folder)] == ["a.js"]
    stamp.stamp_folder(folder)
    text = (folder / "a.js").read_text(encoding="utf-8")
    version = stamp.folder_hash(folder)
    assert f"'./b.js?v={version}'" in text and f"'../c.js?v={version}'" in text
