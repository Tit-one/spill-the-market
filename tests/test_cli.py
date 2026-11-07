import json

from typer.testing import CliRunner


def test_cli_examples_and_doctor(tmp_path):
    from spill_market.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["examples"])
    assert result.exit_code == 0
    assert {item["id"] for item in json.loads(result.stdout)} == {"game", "software"}
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["fts5"] is True


def test_cli_demo_is_complete_and_zero_api(tmp_path):
    from spill_market.cli import app
    output = tmp_path / "report.json"
    result = CliRunner().invoke(app, ["demo", "--data-dir", str(tmp_path / "data"), "--days", "2",
                                    "--population", "60", "--repetitions", "1", "--output", str(output)])
    assert result.exit_code == 0, result.stdout
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["metadata"]["api_calls_during_numeric_simulation"] == 0
    assert len(report["scenarios"]) >= 4
