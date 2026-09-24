"""`python -m collectai_eval run --mode mock|live` (E10-S1).

A thin wrapper: builds the DB engine/policy provider, loads the dataset,
calls `runner.run_eval`, stores the result via `store.store_eval_run`, and
prints `report.render_report`'s output. No evaluation logic lives here.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.config.settings import load_settings
from collectai.types.clock import SystemClock
from collectai.types.enums import ProviderMode
from collectai_eval.datasets.loader import load_dataset
from collectai_eval.report import render_report
from collectai_eval.runner import LiveEvalRefusedError, RunConfig, run_eval
from collectai_eval.store import store_eval_run


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CollectAI evaluation runner")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run the evaluation dataset.")
    run_parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    run_parser.add_argument(
        "--live-confirm",
        action="store_true",
        help="Required (with --mode live) to actually call the real Anthropic API.",
    )
    run_parser.add_argument("--triggered-by", default="cli")
    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = load_settings()
    clock = SystemClock()
    policy_provider = PolicyProvider()
    policy_provider.register(load_seed_policy_v1(clock))
    policy_provider.activate("policy-v1", clock)

    engine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    dataset = load_dataset()
    mode = ProviderMode.LIVE if args.mode == "live" else ProviderMode.MOCK
    config = RunConfig(
        mode=mode,
        triggered_by=args.triggered_by,
        live_confirmed=args.live_confirm,
        anthropic_api_key=(
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        ),
        anthropic_model=settings.anthropic_model,
    )

    try:
        async with session_factory() as session:
            result = await run_eval(
                session,
                session_factory=session_factory,
                dataset=dataset,
                config=config,
                clock=clock,
                policy_provider=policy_provider,
            )
            eval_run_id = await store_eval_run(session, result)
    except LiveEvalRefusedError as exc:
        print(f"LIVE evaluation refused: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()

    print(render_report(result))
    print(f"\nStored as eval_run_id={eval_run_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if args.command == "run":
        return asyncio.run(_run(args))
    return 1  # pragma: no cover - argparse's `required=True` already rejects this


if __name__ == "__main__":
    raise SystemExit(main())
