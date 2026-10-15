from masguardeval.stats import summarize_trials


def test_trial_summary_clusters_repeats_by_scenario_and_handles_na():
    def result(scenario, before, after, applicable=True):
        return {
            "architecture": "multi", "scenario": {"scenario_id": scenario},
            "baseline_metrics": {"RSS": {"score": before, "applicable": applicable}, "CFP": {"score": 0, "applicable": False}},
            "guarded_metrics": {"RSS": {"score": after, "applicable": applicable}, "CFP": {"score": 0, "applicable": False}},
        }

    analysis = summarize_trials([result("a", 0, 1), result("a", 0, 0.5), result("b", 0, 0.25), result("c", 0, 1, False)], bootstrap_samples=200)
    rss = analysis["architectures"]["multi"]["RSS"]
    assert rss["scenario_n"] == 2
    assert rss["trial_pair_n"] == 3
    assert rss["mean_improvement"] == 0.5
    assert rss["ci_95_scenario_bootstrap"] == [0.25, 0.75]
    assert "CFP" not in analysis["architectures"]["multi"]
