"""
sentinel/tests/test_alpr_benchmark.py
======================================
Unit tests for PlateSynthesizer and ALPRBenchmarkRunner.
"""

from sentinel.alpr.benchmark import PlateSynthesizer, ALPRBenchmarkRunner


def test_plate_synthesis():
    synth = PlateSynthesizer(width=300, height=80)
    img = synth.generate_plate_image("UP32AB1234")
    assert img is not None
    assert img.shape == (80, 300, 3)

    distorted = synth.apply_distortions(img, motion_blur=True, sensor_noise=True, low_light=True)
    assert distorted is not None
    assert distorted.shape == img.shape


def test_benchmark_runner_pass():
    runner = ALPRBenchmarkRunner()
    results = runner.run_benchmark(num_samples=10)
    assert results["num_samples"] == 10
    assert results["accuracy_percent"] >= 90.0
    assert results["sih_pass"] is True
    assert results["avg_latency_ms"] < 100.0
