import pytest

from meterzero import pipeline, simulate


@pytest.fixture(scope="session")
def small_factory(tmp_path_factory):
    """A 16-day simulated factory with an air leak in the last days, trained once per test run."""
    data_dir = tmp_path_factory.mktemp("factory")
    simulate.write(simulate.simulate(days=16, seed=3, leak_day=13), data_dir)
    results = pipeline.run(data_dir, val_days=3, test_days=4, verbose=False)
    results_path = data_dir / "results.pkl"
    pipeline.save(results, results_path)
    return data_dir, results_path, results
