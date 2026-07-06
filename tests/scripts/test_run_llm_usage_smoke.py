from scripts import run_llm_usage_smoke


def test_fixture_smoke_reports_openrouter_and_gemini_usage_without_live_api():
    result = run_llm_usage_smoke.run_fixture_smoke()

    assert result["status"] == "passed"
    assert result["openrouter"]["estimated_cost"] == 0.00042
    assert result["openrouter"]["total_tokens"] == 22
    assert result["gemini"]["estimated_cost"] == 0.5
    assert result["gemini"]["total_tokens"] == 2_000_000


def test_main_defaults_to_fixture_json(capsys):
    exit_code = run_llm_usage_smoke.main(["--json"])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert '"mode": "fixture"' in output
    assert '"status": "passed"' in output
