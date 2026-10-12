"""Stage interfaces reserved for later tasks."""
from argparse import Namespace
from weekly_diff.config import Config


def collect(cfg: Config, args: Namespace) -> None:
    raise NotImplementedError("task 002")


def build(cfg: Config, args: Namespace) -> None:
    raise NotImplementedError("task 004")


def render(cfg: Config, args: Namespace) -> None:
    raise NotImplementedError("task 005")


def publish(cfg: Config, args: Namespace) -> None:
    raise NotImplementedError("task 006")
