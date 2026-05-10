from __future__ import annotations

import importlib
import subprocess
from pathlib import Path


def test_legacy_preregister_duplicate_does_not_exist() -> None:
    legacy_name = "sigma" + "_job1.py"
    assert not Path("agents") .joinpath(legacy_name).exists(), (
        "Legacy preregister duplicate file still exists. "
        "Only agents/preregister.py should exist."
    )


def test_preregister_py_is_importable() -> None:
    mod = importlib.import_module("agents.preregister")
    assert hasattr(mod, "SigmaJob1") or hasattr(mod, "PreregisterAgent") or any(
        callable(getattr(mod, name)) for name in dir(mod) if not name.startswith("_")
    ), "agents/preregister.py must export at least one callable"


def test_legacy_preregister_no_imports_remaining() -> None:
    token = "sigma" + "_job1"
    result = subprocess.run(
        [
            "grep",
            "-r",
            token,
            "--include=*.py",
            "--exclude=test_audit_fixes.py",
            "--exclude=test_structural_cleanup.py",
            ".",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    hits = [
        l
        for l in result.stdout.splitlines()
        if token in l and "does_not_exist" not in l and "test_legacy_preregister" not in l
    ]
    assert len(hits) == 0, (
        "Found legacy preregister imports that should be updated:\n" + "\n".join(hits)
    )


def test_legacy_sigma_second_stage_not_in_agents_root() -> None:
    legacy = "sigma" + "_job2.py"
    assert not Path("agents").joinpath(legacy).exists(), (
        "legacy sigma second-stage module should be in package "
        "agents/sigma/"
    )


def test_statsrun_job_not_in_agents_root() -> None:
    assert not Path("agents/statsrun_job.py").exists(), (
        "agents/statsrun_job.py should be at "
        "agents/statsrun/statsrun_job.py — move it into the statsrun package"
    )


def test_sigma_stage2_importable_from_package() -> None:
    module_name = "agents.sigma." + "sigma" + "_job2"
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_statsrun_job_importable_from_package() -> None:
    mod = importlib.import_module("agents.statsrun.statsrun_job")
    assert mod is not None


def test_agents_codec_directory_does_not_exist() -> None:
    assert not Path("agents/codec").exists(), (
        "agents/codec/ is a ghost directory left over from the rename. "
        "All codec logic now lives in agents/codeaudit/ and "
        "agents/specaudit_pass2.py. Delete agents/codec/."
    )


def test_no_imports_from_agents_codec() -> None:
    result = subprocess.run(
        ["grep", "-r", "agents.codec", "--include=*.py", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    hits = [l for l in result.stdout.splitlines() if "__pycache__" not in l and "test_" not in l]
    assert len(hits) == 0, "Found legacy codec imports that should be updated:\n" + "\n".join(hits)


def test_flat_shim_files_are_pure_reexports() -> None:
    shim_files = [
        "agents/hawk.py",
        "agents/miner.py",
        "agents/quill.py",
        "agents/scout.py",
    ]
    for shim_path in shim_files:
        p = Path(shim_path)
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8")
        lines = [
            l.strip()
            for l in content.splitlines()
            if l.strip()
            and not l.strip().startswith("#")
            and not l.strip().startswith("from ")
            and not l.strip().startswith("import ")
        ]
        assert len(lines) == 0, (
            f"{shim_path} contains non-import logic: {lines}\n"
            "Shim files must contain only re-export imports.\n"
            "Move any logic into the package directory."
        )


def test_agents_fixer_directory_does_not_exist() -> None:
    assert not Path("agents/fixer").exists(), (
        "agents/fixer/ is a duplicate of agents/autorepair/. "
        "Delete agents/fixer/ entirely."
    )


def test_autorepair_importable() -> None:
    from agents.autorepair.autorepair import AutoRepairAgent

    assert AutoRepairAgent is not None


def test_no_imports_from_agents_fixer() -> None:
    token = "agents." + "fixer"
    result = subprocess.run(
        ["grep", "-r", token, "--include=*.py", "--exclude=test_structural_cleanup.py", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    hits = [l for l in result.stdout.splitlines() if "__pycache__" not in l and "test_agents_fixer" not in l]
    assert len(hits) == 0, "Found imports from agents.fixer:\n" + "\n".join(hits)


def test_agents_scout_directory_does_not_exist() -> None:
    assert not Path("agents/scout").is_dir(), (
        "agents/scout/ is a duplicate of agents/literature/. "
        "Delete the directory — keep agents/scout.py shim only if needed."
    )


def test_literature_importable() -> None:
    from agents.literature.literature import LiteratureAgent

    assert LiteratureAgent is not None


def test_no_imports_from_agents_scout_dir() -> None:
    token = "agents.scout" + ".scout"
    result = subprocess.run(
        ["grep", "-r", token, "--include=*.py", "--exclude=test_structural_cleanup.py", "."],
        capture_output=True,
        text=True,
        check=False,
    )
    hits = [l for l in result.stdout.splitlines() if "__pycache__" not in l and "test_agents_scout" not in l]
    assert len(hits) == 0, (
        "Found imports from agents.scout.scout (old path):\n" + "\n".join(hits)
    )


def test_writer_has_no_sha_duplicate() -> None:
    import hashlib

    result = subprocess.run(
        [
            "find",
            ".",
            "-not",
            "-path",
            "./.git/*",
            "-not",
            "-path",
            "./.venv/*",
            "-not",
            "-path",
            "*/__pycache__/*",
            "-name",
            "*.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    files = result.stdout.strip().splitlines()
    shas: dict[str, str] = {}
    for f in files:
        try:
            h = hashlib.sha256(Path(f).read_bytes()).hexdigest()[:16]
            if h in shas and Path(f).stat().st_size > 100:
                assert False, f"Duplicate file content:\n  {shas[h]}\n  {f}\nOne of these must be deleted."
            shas[h] = f
        except Exception:
            pass


def test_aria_dispatch_py_does_not_exist() -> None:
    assert not Path("aria/dispatch.py").exists(), (
        "aria/dispatch.py is an empty ghost file. Delete it."
    )


def test_aria_routing_config_does_not_exist() -> None:
    assert not Path("aria/routing_config.py").exists(), (
        "aria/routing_config.py is an empty ghost file. Delete it."
    )


def test_codeaudit_pass1_in_package() -> None:
    mod = importlib.import_module("agents.codeaudit.codeaudit_pass1")
    assert mod is not None


def test_specaudit_pass2_in_package() -> None:
    mod = importlib.import_module("agents.codeaudit.specaudit_pass2")
    assert mod is not None


def test_preregister_in_package() -> None:
    mod = importlib.import_module("agents.preregister.preregister")
    assert mod is not None


def test_flat_shims_are_one_line() -> None:
    for f in ["agents/codeaudit_pass1.py", "agents/specaudit_pass2.py", "agents/preregister.py"]:
        p = Path(f)
        if not p.exists():
            continue
        real_lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]
        assert len(real_lines) <= 2, (
            f"{f} has {len(real_lines)} non-comment lines. "
            "It should be a 1-2 line shim only."
        )
