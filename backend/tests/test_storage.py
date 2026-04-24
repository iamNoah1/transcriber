from pathlib import Path

from app.storage import Storage


def test_create_job_dirs_returns_paths(tmp_path: Path):
    s = Storage(tmp_path)
    paths = s.create_job_dirs("job-1")
    assert paths.input.is_dir() and paths.input.name == "input"
    assert paths.output.is_dir() and paths.output.name == "output"
    assert paths.root == tmp_path / "jobs" / "job-1"


def test_sanitise_filename_strips_paths_and_nulls():
    s = Storage(Path("/"))
    assert s.sanitise_filename("../../etc/passwd") == "passwd"
    assert s.sanitise_filename("a\x00b.txt") == "ab.txt"
    assert s.sanitise_filename("") == "upload"


def test_zip_output_produces_archive_with_contents(tmp_path: Path):
    s = Storage(tmp_path)
    paths = s.create_job_dirs("job-z")
    (paths.output / "a.txt").write_text("hello")
    (paths.output / "b.txt").write_text("world")
    zip_path = s.zip_output("job-z")
    assert zip_path.is_file()
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(z.namelist())
    assert names == ["a.txt", "b.txt"]


def test_single_output_no_zip(tmp_path: Path):
    s = Storage(tmp_path)
    paths = s.create_job_dirs("job-s")
    f = paths.output / "only.txt"
    f.write_text("x")
    single = s.single_output_file("job-s")
    assert single == f


def test_delete_job_tree(tmp_path: Path):
    s = Storage(tmp_path)
    s.create_job_dirs("job-d")
    s.delete_job("job-d")
    assert not (tmp_path / "jobs" / "job-d").exists()
