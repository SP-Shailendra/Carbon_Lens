import subprocess
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]


def project_config():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_dependency_groups_are_pinned_and_separate():
    config = project_config()
    runtime = [
        Requirement(line)
        for line in (ROOT / "requirements.txt").read_text().splitlines()
        if line.strip()
    ]
    development = [
        Requirement(value) for value in config["project"]["optional-dependencies"]["dev"]
    ]
    for requirement in runtime + development:
        pins = list(requirement.specifier)
        assert len(pins) == 1 and pins[0].operator == "=="
        assert "*" not in pins[0].version
    runtime_names = {requirement.name for requirement in runtime}
    dev_names = {requirement.name for requirement in development}
    assert {"pytest", "ruff", "mypy"} <= dev_names
    assert not runtime_names & dev_names
    assert (ROOT / "requirements-dev.txt").read_text().strip() == "-e .[dev]"
    assert config["tool"]["setuptools"]["dynamic"]["dependencies"]["file"] == ["requirements.txt"]


def test_release_metadata_and_api_version_match():
    from carbonlens.api import create_app

    config = project_config()
    assert config["project"]["version"] == "0.1.0"
    assert create_app().version == config["project"]["version"]
    assert config["project"]["license"] == "LicenseRef-Proprietary"
    for filename in ("LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", ".github/workflows/ci.yml"):
        assert (ROOT / filename).is_file()


def test_maintained_text_files_use_lf():
    roots = [ROOT / folder for folder in ("src", "tests", "data", "docs", ".github", ".streamlit")]
    candidates = [path for path in ROOT.iterdir() if path.is_file()]
    for root in roots:
        candidates.extend(path for path in root.rglob("*") if path.is_file())
    text_suffixes = {".py", ".toml", ".md", ".txt", ".yaml", ".yml", ".csv"}
    text_names = {
        ".gitattributes",
        ".gitignore",
        ".dockerignore",
        ".env.example",
        "Dockerfile",
        "LICENSE",
    }
    for path in candidates:
        if any(part.endswith(".egg-info") for part in path.parts):
            continue
        if path.suffix in text_suffixes or path.name in text_names:
            assert b"\r" not in path.read_bytes(), f"Non-LF line ending: {path.relative_to(ROOT)}"


def test_ignore_policy_covers_generated_artifacts():
    patterns = set((ROOT / ".gitignore").read_text().splitlines())
    assert {
        ".local/",
        "*.db",
        "*.db-shm",
        "*.db-wal",
        "__pycache__/",
        "*.py[cod]",
        ".pytest_cache/",
        ".ruff_cache/",
        ".mypy_cache/",
        "*.egg-info/",
        "build/",
        "dist/",
    } <= patterns
    assert "* text=auto eol=lf" in (ROOT / ".gitattributes").read_text()


def test_generated_artifacts_are_not_tracked():
    if not (ROOT / ".git").exists():
        pytest.skip("Source snapshot has no Git metadata; tracked-file check runs in GitHub CI.")
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    forbidden_directories = {
        ".local",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".venv",
        "build",
        "dist",
    }
    for filename in result.stdout.decode().split("\0"):
        path = Path(filename)
        assert not forbidden_directories.intersection(path.parts), filename
        assert not any(part.endswith(".egg-info") for part in path.parts), filename
        assert path.suffix not in {".db", ".sqlite", ".sqlite3", ".pyc", ".pyo"}, filename
        assert not filename.endswith((".db-wal", ".db-shm")), filename
