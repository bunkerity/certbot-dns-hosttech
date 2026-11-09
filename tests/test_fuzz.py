"""Keep fuzz entry points executable and ensure their assertions catch regressions."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("atheris")


def test_fuzz_targets_accept_seed_inputs():
    spec = importlib.util.spec_from_file_location("fuzz_hosttech", Path(__file__).parents[1] / "fuzz/fuzz_hosttech.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for target in (module.fuzz_zones, module.fuzz_credentials, module.fuzz_api):
        for data in (b"", b"example.com", b"\x00\xff\x01", bytes(range(256))):
            target(data)
