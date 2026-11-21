import sys

import pytest

import lazy_imports


@pytest.fixture
def hooks(tmp_path, monkeypatch):
    """Install the hooks for fake packages in a temporary directory."""
    (tmp_path / "wose_fake_installed").mkdir()
    (tmp_path / "wose_fake_installed" / "__init__.py").write_text("LOADED = True\ndef double(x):\n    return 2 * x\nclass Thing:\n    pass\n")
    (tmp_path / "wose_fake_installed" / "sub.py").write_text("VALUE = 42\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    state = lazy_imports._hooks
    monkeypatch.setattr(state, "deferred", {})
    monkeypatch.setattr(state, "loaded", set())
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    lazy_imports.install(
        deferred_installed=["wose_fake_installed"],
        deferred_packages=["wose_fake_missing"],
        stub_prefixes=["wose_fake_stub"],
    )
    yield
    for name in list(sys.modules):
        if name.startswith("wose_fake"):
            del sys.modules[name]


def test_deferred_installed_module(hooks):
    from wose_fake_installed import double, Thing
    from wose_fake_installed.sub import VALUE

    assert not lazy_imports._hooks.is_loaded("wose_fake_installed")
    assert double(4) == 8
    assert lazy_imports._hooks.is_loaded("wose_fake_installed")
    assert isinstance(Thing(), Thing)
    # Values imported before loading stay proxies; attribute access on the
    # module works normally once loaded.
    assert isinstance(VALUE, lazy_imports._LazyAttribute)
    import wose_fake_installed.sub

    assert wose_fake_installed.sub.VALUE == 42


def test_deferred_missing_package(hooks):
    import wose_fake_missing as missing
    from wose_fake_missing import solve

    with pytest.raises(lazy_imports.MissingPackages) as e:
        solve()
    assert e.value.packages == ["wose_fake_missing"]
    # Not caught by `except Exception`
    assert not isinstance(e.value, Exception)
    with pytest.raises(lazy_imports.MissingPackages):
        missing.something()


def test_stub_module(hooks):
    from wose_fake_stub.deep import njit, Anything

    @njit
    def f():
        return 1

    @njit(cache=True)
    def g():
        return 2

    assert f() == 1
    assert g() == 2
    Anything().whatever()
