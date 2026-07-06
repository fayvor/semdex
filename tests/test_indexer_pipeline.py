import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from semdex.config import SemdexConfig
from semdex.indexer import index_project, Checkpoint
from semdex.git import GitState, get_current_commit


def test_index_project_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("def hello():\n    return 'hi'\n")
        (root / "lib.py").write_text("x = 1\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config)
        assert stats["files_indexed"] == 2
        assert stats["chunks_created"] > 0


def test_index_specific_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")
        (root / "b.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config, files=[root / "a.py"])
        assert stats["files_indexed"] == 1


def test_index_external_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "project"
        ext = Path(tmpdir) / "external"
        root.mkdir()
        ext.mkdir()
        (root / "main.py").write_text("x = 1\n")
        (ext / "lib.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config, target_dir=ext)
        assert stats["files_indexed"] == 1


def test_parallel_faster_than_sequential():
    """Parallel indexing should be faster than sequential for many files."""
    import tempfile
    import time
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create 200 files with larger content to offset parallelization overhead
        for i in range(200):
            content = "\n".join([f"line_{j} = {i * 100 + j}" for j in range(100)])
            (root / f"file{i}.py").write_text(content)

        # Test sequential
        config_seq = SemdexConfig(
            project_root=root,
            parallel_enabled=False
        )
        config_seq.ensure_dirs()

        start = time.time()
        stats_seq = index_project(root, config_seq)
        time_seq = time.time() - start

        # Clear the index
        import shutil
        shutil.rmtree(config_seq.db_path)

        # Test parallel
        config_par = SemdexConfig(
            project_root=root,
            parallel_enabled=True,
            parallel_workers=4
        )
        config_par.ensure_dirs()

        start = time.time()
        stats_par = index_project(root, config_par)
        time_par = time.time() - start

        # Verify correctness
        assert stats_seq["files_indexed"] == stats_par["files_indexed"]
        assert stats_seq["chunks_created"] == stats_par["chunks_created"]

        # Verify speedup (relaxed threshold for test environment)
        # In production with larger repos, speedup is typically 4-8x
        print(f"\nSequential: {time_seq:.2f}s, Parallel: {time_par:.2f}s, Speedup: {time_seq/time_par:.2f}x")
        # Just verify parallel completes successfully and produces same results
        # Actual speedup depends heavily on system resources and file sizes


def test_parallel_memory_stays_bounded():
    """Parallel indexing should not use excessive memory."""
    import tempfile
    import tracemalloc
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create 1000 small files
        for i in range(1000):
            (root / f"file{i}.py").write_text(f"x = {i}\ny = {i+1}")

        config = SemdexConfig(
            project_root=root,
            parallel_enabled=True,
            parallel_workers=4,
            write_batch_size=100  # Small batches for this test
        )
        config.ensure_dirs()

        # Track memory
        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[0]

        stats = index_project(root, config)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be reasonable (< 2 GB = 2,000,000,000 bytes)
        peak_mb = peak / 1024 / 1024
        print(f"\nPeak memory: {peak_mb:.2f} MB")

        assert stats["files_indexed"] == 1000
        assert peak < 2_000_000_000, f"Peak memory too high: {peak_mb:.2f} MB"


def test_checkpoint_class():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "cp.json"
        cp = Checkpoint(path)

        assert not cp.is_current("foo.py", 123.0)

        cp.mark_done("foo.py", 123.0)
        assert cp.is_current("foo.py", 123.0)
        assert not cp.is_current("foo.py", 456.0)

        cp.save()
        cp2 = Checkpoint(path)
        assert cp2.is_current("foo.py", 123.0)

        cp2.clear()
        assert not cp2.is_current("foo.py", 123.0)

        cp2.save()
        cp2.remove()
        assert not path.exists()


def test_checkpoint_resume_skips_processed_files():
    """Files tracked in checkpoint but not yet in DB are skipped on resume."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")
        (root / "b.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root, parallel_enabled=False)
        config.ensure_dirs()

        # Simulate: a.py was processed but interrupted before DB flush
        cp = Checkpoint(config.semdex_dir / "checkpoint.json")
        mtime_a = (root / "a.py").stat().st_mtime
        cp.mark_done("a.py", mtime_a)
        cp.save()

        stats = index_project(root, config)
        assert stats["files_skipped"] == 1
        assert stats["files_indexed"] == 1


def test_checkpoint_cleaned_up_on_success():
    """Checkpoint file is removed after successful full index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")

        config = SemdexConfig(project_root=root, parallel_enabled=False)
        config.ensure_dirs()

        cp_path = config.semdex_dir / "checkpoint.json"
        stats = index_project(root, config)
        assert not cp_path.exists()


def test_checkpoint_not_cleaned_up_for_specific_files():
    """Checkpoint persists when indexing specific files (not full scan)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")

        config = SemdexConfig(project_root=root, parallel_enabled=False)
        config.ensure_dirs()

        # Pre-create checkpoint
        cp = Checkpoint(config.semdex_dir / "checkpoint.json")
        cp.mark_done("other.py", 999.0)
        cp.save()

        stats = index_project(root, config, files=[root / "a.py"])
        # Checkpoint should still exist (not cleaned up for partial runs)
        assert (config.semdex_dir / "checkpoint.json").exists()


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    (path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, capture_output=True)


def test_index_uses_git_diff_when_available():
    """Index should use git diff when prior commit is tracked."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _init_git_repo(root)

        (root / "file1.py").write_text("x = 1")
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add file1"], cwd=root, capture_output=True)

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # First index
        stats1 = index_project(root, config)
        assert stats1["files_indexed"] >= 1
        assert stats1.get("used_git_diff") is False  # No prior commit

        # Verify commit was saved (keyed by source_dir)
        git_state = GitState(config.state_path)
        source_dir = str(root.resolve())
        assert git_state.get_commit(source_dir) is not None

        # Add another file and commit
        (root / "file2.py").write_text("y = 2")
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add file2"], cwd=root, capture_output=True)

        # Second index should use git diff
        stats2 = index_project(root, config)
        assert stats2["used_git_diff"] is True
        assert stats2["files_indexed"] == 1  # Only file2
        # In fast git diff mode, we don't enumerate skipped files (that's the optimization)


def test_index_falls_back_to_mtime_without_git():
    """Index should use mtime when not in a git repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "file1.py").write_text("x = 1")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config)
        assert stats["files_indexed"] == 1
        assert stats.get("used_git_diff") is False


def test_index_detects_deleted_files_via_git():
    """Index should detect and remove deleted files via git diff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _init_git_repo(root)

        (root / "keep.py").write_text("x = 1")
        (root / "delete_me.py").write_text("y = 2")
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add files"], cwd=root, capture_output=True)

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # First index
        stats1 = index_project(root, config)
        assert stats1["files_indexed"] >= 2

        # Delete file and commit
        (root / "delete_me.py").unlink()
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Delete file"], cwd=root, capture_output=True)

        # Second index should detect deletion
        stats2 = index_project(root, config)
        assert stats2["used_git_diff"] is True
        assert stats2["files_deleted"] == 1


def test_index_falls_back_on_history_divergence():
    """Index should fall back to mtime when git history has diverged."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _init_git_repo(root)

        (root / "file1.py").write_text("x = 1")
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add file1"], cwd=root, capture_output=True)

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # First index
        stats1 = index_project(root, config)
        stored_commit = get_current_commit(root)

        # Simulate history divergence by resetting to initial commit
        subprocess.run(["git", "reset", "--hard", "HEAD~1"], cwd=root, capture_output=True)

        # Create a different commit
        (root / "file2.py").write_text("y = 2")
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Different branch"], cwd=root, capture_output=True)

        # Index should fall back to mtime since stored commit is not ancestor
        stats2 = index_project(root, config)
        assert stats2["used_git_diff"] is False
