"""Command-line entry point for the weekly pipeline."""
import argparse
from datetime import datetime, timezone
import logging
import os
from pathlib import Path

from weekly_diff import pipeline
from weekly_diff.config import Config, ConfigError, load_config
from weekly_diff.dates import issue_id_for, parse_issue_id
from weekly_diff.log import redact, setup_logging


def _issue_id(value: str) -> str:
    try:
        parse_issue_id(value)
    except ValueError:
        raise argparse.ArgumentTypeError("issue must be a valid ISO YYYY-WW") from None
    return value


def _options(parser: argparse.ArgumentParser, suppress: bool = False) -> None:
    def default(value: object) -> object:
        return argparse.SUPPRESS if suppress else value

    parser.add_argument("--config", default=default("config.yaml"), metavar="PATH")
    parser.add_argument("--dry-run", action="store_true", default=default(False))
    parser.add_argument("--issue", type=_issue_id, default=default(None), metavar="YYYY-WW")
    parser.add_argument("-v", "--verbose", action="store_true", default=default(False))


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _options(parser)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("collect", "build", "render", "publish", "status"):
        sub = commands.add_parser(command)
        _options(sub, suppress=True)
        if command == "publish":
            sub.add_argument("--preview", action="store_true")
        elif command == "status":
            sub.add_argument("--github-output", action="store_true")
    return parser


def _status(cfg: Config, args: argparse.Namespace) -> None:
    values = {
        "paused": str(cfg.paused).lower(),
        "publish_enabled": str(cfg.publish_enabled).lower(),
        "issue_id": args.issue,
    }
    print(redact(f"name={cfg.name}"))
    for key, value in values.items():
        print(redact(f"{key}={value}"))
    if args.github_output:
        destination = os.environ.get("GITHUB_OUTPUT")
        if not destination:
            raise RuntimeError("GITHUB_OUTPUT is not set")
        with Path(destination).open("a", encoding="utf-8") as stream:
            stream.write("".join(f"{key}={value}\n" for key, value in values.items()))


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    setup_logging(args.verbose)
    args.issue = args.issue or issue_id_for(datetime.now(timezone.utc))
    try:
        cfg = load_config(args.config)
        if args.command == "status":
            _status(cfg, args)
        else:
            getattr(pipeline, args.command)(cfg, args)
    except ConfigError as error:
        logging.error("%s", error, exc_info=args.verbose)
        return 2
    except Exception as error:
        logging.error("%s", error, exc_info=args.verbose)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
