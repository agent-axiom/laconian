from laconian_eval import __version__
from laconian_eval.cli import main


def test_package_exposes_alpha_version() -> None:
    assert __version__ == "0.1.0a1"


def test_cli_reports_alpha_version(capsys) -> None:
    assert main(["--version"], program="laconian") == 0
    assert capsys.readouterr().out.strip() == "laconian 0.1.0a1"
