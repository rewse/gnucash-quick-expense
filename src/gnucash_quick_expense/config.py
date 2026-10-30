"""The YAML file that names which accounts the form offers."""

import pathlib
from typing import NamedTuple

import yaml


class ConfigError(ValueError):
    """A configuration file that cannot be used."""


class AccountChoice(NamedTuple):
    """Accounts offered in one list, and the one selected at first."""

    patterns: tuple[str, ...]
    default: str | None


class Config(NamedTuple):
    """The account lists of the form."""

    from_accounts: AccountChoice
    to_accounts: AccountChoice


def matches(pattern: str, path: str) -> bool:
    """Tells whether an account path matches a pattern.

    Both are split at ":". In the pattern, "*" matches exactly one account
    name, "**" matches one or more, and anything else matches the same name,
    case-sensitively.
    """
    return _matches(pattern.split(":"), path.split(":"))


def _matches(pattern: list[str], names: list[str]) -> bool:
    if not pattern:
        return not names
    if not names:
        return False
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_matches(rest, names[i:]) for i in range(1, len(names) + 1))
    if head != "*" and head != names[0]:
        return False
    return _matches(rest, names[1:])


def _choice(data: object, key: str) -> AccountChoice:
    section = data.get(key) if isinstance(data, dict) else None
    if not isinstance(section, dict):
        raise ConfigError(f"{key} must be a mapping")
    patterns = section.get("patterns")
    if (
        not isinstance(patterns, list)
        or not patterns
        or not all(isinstance(p, str) and p for p in patterns)
    ):
        raise ConfigError(f"{key}.patterns must be a non-empty list of strings")
    default = section.get("default")
    if default is not None and not isinstance(default, str):
        raise ConfigError(f"{key}.default must be a string")
    return AccountChoice(tuple(patterns), default)


def load(path: pathlib.Path) -> Config:
    """Reads and validates a configuration file.

    Raises:
        ConfigError: The file is not valid YAML or does not have the
            expected shape.
        OSError: The file cannot be read.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML: {e}") from e
    return Config(_choice(data, "from_accounts"), _choice(data, "to_accounts"))
