from laconian_eval import __version__
from laconian_eval.cli import main


def test_package_exposes_development_version() -> None:
    assert __version__ == "0.1.0.dev0"


def test_cli_reports_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "laconian 0.1.0.dev0"
