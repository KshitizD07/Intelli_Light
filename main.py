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


def run_sentinel_demo(_args):
    """Launch the Sentinel ANPR trajectory tracking and intercept demo."""
    from sentinel.demo import main as demo_main

    demo_main()


def run_sentinel_web(args):
    """Launch the Sentinel live GIS surveillance dashboard."""
    import uvicorn
    import os

    print(f"Starting Sentinel Web Intelligence Dashboard on http://{args.host}:{args.port}")
    uvicorn.run("sentinel.server:app", host=args.host, port=args.port, reload=False)


def run_sentinel_gui(args):
    """Launch the real-time Sentinel + Intelli-Light SUMO GUI visualizer."""
    from sentinel.gui_demo import run_gui_scenario
    from pathlib import Path

    cfg = args.cfg or str(Path(__file__).parent / "simulation" / "lucknow_map" / "lucknow.sumocfg")
    run_gui_scenario(
        cfg_file=cfg,
        target_plate=args.plate,
        use_gui=not args.no_gui,
        delay_ms=args.delay,
        max_steps=args.max_steps,
        auto_intercept_step=args.intercept_step,
        manual_mode=not getattr(args, "auto", False),
        scale=getattr(args, "scale", 1.0),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="intelli-light",
        description="Intelli-Light 3.0 & Sentinel Urban Intelligence Platform",
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

    sentinel_demo_p = subparsers.add_parser(
        "sentinel-demo",
        help="Launch the turnkey Sentinel ANPR trajectory tracking & intercept demo",
    )
    sentinel_demo_p.set_defaults(func=run_sentinel_demo)

    sentinel_web_p = subparsers.add_parser(
        "sentinel-web",
        help="Launch the Sentinel real-time Web GIS surveillance dashboard",
    )
    sentinel_web_p.add_argument("--host", default="0.0.0.0", help="Host interface")
    sentinel_web_p.add_argument("--port", type=int, default=8888, help="Port")
    sentinel_web_p.set_defaults(func=run_sentinel_web)

    sentinel_gui_p = subparsers.add_parser(
        "sentinel-gui",
        help="Launch the Sentinel + Intelli-Light real-time SUMO-GUI physical demonstration",
    )
    sentinel_gui_p.add_argument("--cfg", default="", help="Path to lucknow.sumocfg")
    sentinel_gui_p.add_argument("--plate", default="UP32XY9999", help="Target license plate")
    sentinel_gui_p.add_argument("--no-gui", action="store_true", help="Run without GUI (headless)")
    sentinel_gui_p.add_argument("--delay", type=int, default=80, help="Delay per step in ms")
    sentinel_gui_p.add_argument("--max-steps", type=int, default=800, help="Maximum steps")
    sentinel_gui_p.add_argument("--intercept-step", type=int, default=35, help="Step to authorize intercept")
    sentinel_gui_p.add_argument("--auto", action="store_true", help="Auto-trigger intercept instead of waiting for manual [SPACE]/[R]")
    sentinel_gui_p.add_argument("--scale", type=float, default=1.0, help="Traffic demand scale factor (e.g. 5.0 for 5x traffic)")
    sentinel_gui_p.set_defaults(func=run_sentinel_gui)

    args = parser.parse_args()
    args.func(args)
