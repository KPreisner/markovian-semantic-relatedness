import msr


def test_version_matches_distribution_metadata() -> None:
    assert msr.__version__ == "0.1.0"
