"""
Intelli-Light GNN CLI
=====================

Single entry point for the current GNN/ST-MARL development path.

The repository currently has no valid trained production checkpoint. Existing
prototype checkpoints were removed to avoid confusing mock-trained artifacts
with a real traffic-control model.
"""

import argparse


def run_train_gnn(_args):
    """Run the GNN training script on randomized maps with EV/accidents safely."""
    from training.train_gnn_randomized import main as train_gnn_main

    train_gnn_main()


def run_train_st_marl(_args):
    """Run the current spatio-temporal MARL training script."""
    from training.train_st_marl import main as train_st_marl_main

    train_st_marl_main()


def run_test_sumo_gnn(_args):
    """Run the SUMO GNN environment smoke test."""
    from training.test_sumo_gnn import main as test_sumo_gnn_main

    test_sumo_gnn_main()


def run_gnn_gui(_args):
    """Launch the SUMO GUI GNN demonstration."""
    from training.run_gnn_gui import main as run_gnn_gui_main

    run_gnn_gui_main()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="intelli-light",
        description="Intelli-Light GNN research CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    train_gnn_p = subparsers.add_parser(
        "train-gnn",
        help="Run the current GNN architecture training script",
    )
    train_gnn_p.set_defaults(func=run_train_gnn)

    train_st_marl_p = subparsers.add_parser(
        "train-st-marl",
        help="Run the current GAT+LSTM ST-MARL training script",
    )
    train_st_marl_p.set_defaults(func=run_train_st_marl)

    test_sumo_gnn_p = subparsers.add_parser(
        "test-sumo-gnn",
        help="Smoke-test the SUMO GNN environment with random actions",
    )
    test_sumo_gnn_p.set_defaults(func=run_test_sumo_gnn)

    gnn_gui_p = subparsers.add_parser(
        "gnn-gui",
        help="Launch the SUMO GUI GNN demonstration",
    )
    gnn_gui_p.set_defaults(func=run_gnn_gui)

    args = parser.parse_args()
    args.func(args)
