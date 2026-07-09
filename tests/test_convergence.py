"""Tests for self-play convergence analysis and Elo ratings."""

import numpy as np
import pytest

from rl.analysis.elo import EloRating, EloConfig
from rl.analysis.convergence import ConvergenceTracker, ConvergenceConfig


class TestEloRating:
    def test_winner_gains_rating(self):
        elo = EloRating()
        elo.update("alice", "bob", 1.0)
        assert elo.get_rating("alice") > 1500.0
        assert elo.get_rating("bob") < 1500.0

    def test_loser_loses_rating(self):
        elo = EloRating()
        elo.update("alice", "bob", 0.0)
        assert elo.get_rating("alice") < 1500.0
        assert elo.get_rating("bob") > 1500.0

    def test_draw_from_equal_unchanged(self):
        elo = EloRating()
        elo.update("alice", "bob", 0.5)
        # From equal ratings, a draw should leave ratings approximately unchanged
        assert elo.get_rating("alice") == pytest.approx(1500.0, abs=0.1)
        assert elo.get_rating("bob") == pytest.approx(1500.0, abs=0.1)

    def test_rating_sum_approximately_conserved(self):
        elo = EloRating(EloConfig(k_decay=0.0))  # no decay for exact conservation
        # Play many games
        results = [1.0, 0.0, 0.5, 1.0, 0.0, 1.0, 0.5, 0.0]
        for r in results:
            elo.update("alice", "bob", r)
        total = elo.get_rating("alice") + elo.get_rating("bob")
        assert total == pytest.approx(3000.0, abs=0.1)

    def test_rank_ordering(self):
        elo = EloRating()
        # Alice always wins
        for _ in range(10):
            elo.update("alice", "bob", 1.0)
            elo.update("alice", "carol", 1.0)
        ranking = elo.rank()
        assert ranking[0][0] == "alice"

    def test_k_factor_decay(self):
        config = EloConfig(base_k=32.0, k_decay=0.1)
        elo = EloRating(config)
        # First game: full K
        elo.update("alice", "bob", 1.0)
        first_gain = elo.get_rating("alice") - 1500.0

        # Reset and play with many games already
        elo2 = EloRating(config)
        for _ in range(20):
            elo2.update("alice", "bob", 0.5)  # draws to get games up
        before = elo2.get_rating("alice")
        elo2.update("alice", "bob", 1.0)
        later_gain = elo2.get_rating("alice") - before

        assert later_gain < first_gain  # K decayed

    def test_expected_score_symmetric(self):
        elo = EloRating()
        e_a = elo.expected_score("alice", "bob")
        e_b = elo.expected_score("bob", "alice")
        assert e_a + e_b == pytest.approx(1.0)


class TestConvergenceTracker:
    def test_not_converged_initially(self):
        tracker = ConvergenceTracker()
        assert not tracker.is_converged()

    def test_converges_when_exploitability_low(self):
        config = ConvergenceConfig(
            exploitability_threshold=0.1,
            win_rate_slope_epsilon=0.01,
            consecutive_required=3,
            plateau_window=5,
        )
        tracker = ConvergenceTracker(config)
        # Feed consistent low exploitability and flat win rate
        for i in range(10):
            tracker.update(f"ckpt_{i}", {
                "exploitability": 0.02,
                "win_rate": 0.5 + 0.001 * (i % 2),  # barely changing
            })
        assert tracker.is_converged()

    def test_not_converged_high_exploitability(self):
        config = ConvergenceConfig(
            exploitability_threshold=0.05,
            consecutive_required=3,
        )
        tracker = ConvergenceTracker(config)
        for i in range(10):
            tracker.update(f"ckpt_{i}", {
                "exploitability": 0.5,  # way above threshold
                "win_rate": 0.5,
            })
        assert not tracker.is_converged()

    def test_win_rate_slope_detects_plateau(self):
        tracker = ConvergenceTracker(ConvergenceConfig(plateau_window=5))
        # Flat win rate
        for i in range(10):
            tracker.update(f"ckpt_{i}", {"win_rate": 0.5, "exploitability": 0.01})
        slope = tracker.win_rate_slope()
        assert abs(slope) < 0.01

    def test_win_rate_slope_detects_improvement(self):
        tracker = ConvergenceTracker(ConvergenceConfig(plateau_window=10))
        # Improving win rate
        for i in range(10):
            tracker.update(f"ckpt_{i}", {"win_rate": 0.4 + 0.05 * i, "exploitability": 0.01})
        slope = tracker.win_rate_slope()
        assert slope > 0.01

    def test_nash_gap_non_negative(self):
        tracker = ConvergenceTracker()
        tracker.update("ckpt_0", {
            "exploitability_p1": 0.1,
            "exploitability_p2": 0.2,
            "win_rate": 0.5,
        })
        summary = tracker.summary()
        assert summary["latest_nash_gap"] >= 0
        assert summary["latest_nash_gap"] == pytest.approx(0.2)

    def test_policy_stability_zero_for_identical(self):
        tracker = ConvergenceTracker()
        dist = np.array([0.2, 0.3, 0.1, 0.3, 0.1])
        tracker.update("ckpt_0", {"action_distribution": dist, "win_rate": 0.5, "exploitability": 0.01})
        tracker.update("ckpt_1", {"action_distribution": dist, "win_rate": 0.5, "exploitability": 0.01})
        summary = tracker.summary()
        assert summary["latest_kl_divergence"] == pytest.approx(0.0, abs=1e-8)

    def test_num_checkpoints_tracks_updates(self):
        tracker = ConvergenceTracker()
        for i in range(5):
            tracker.update(f"ckpt_{i}", {"win_rate": 0.5, "exploitability": 0.1})
        assert tracker.num_checkpoints == 5
