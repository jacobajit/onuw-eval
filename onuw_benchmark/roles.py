from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    VILLAGER = "Villager"
    WEREWOLF = "Werewolf"
    SEER = "Seer"
    ROBBER = "Robber"
    TROUBLEMAKER = "Troublemaker"
    DRUNK = "Drunk"
    INSOMNIAC = "Insomniac"
    MINION = "Minion"
    MASON = "Mason"
    HUNTER = "Hunter"
    TANNER = "Tanner"
    DOPPELGANGER = "Doppelganger"


WAKE_ORDER: tuple[Role, ...] = (
    Role.DOPPELGANGER,
    Role.WEREWOLF,
    Role.MINION,
    Role.MASON,
    Role.SEER,
    Role.ROBBER,
    Role.TROUBLEMAKER,
    Role.DRUNK,
    Role.INSOMNIAC,
)

NO_WAKE_ROLES: frozenset[Role] = frozenset({Role.VILLAGER, Role.HUNTER, Role.TANNER})

VILLAGE_ROLES: frozenset[Role] = frozenset(
    {
        Role.VILLAGER,
        Role.SEER,
        Role.ROBBER,
        Role.TROUBLEMAKER,
        Role.DRUNK,
        Role.INSOMNIAC,
        Role.MASON,
        Role.HUNTER,
    }
)

SUPPORTED_NIGHT_ACTION_ROLES: frozenset[Role] = frozenset(
    {
        Role.WEREWOLF,
        Role.MINION,
        Role.MASON,
        Role.SEER,
        Role.ROBBER,
        Role.TROUBLEMAKER,
        Role.DRUNK,
        Role.INSOMNIAC,
    }
)


def parse_role(value: str | Role) -> Role:
    if isinstance(value, Role):
        return value
    normalized = value.strip().lower().replace("_", "").replace("-", "").replace(" ", "")
    aliases = {
        "villager": Role.VILLAGER,
        "werewolf": Role.WEREWOLF,
        "wolf": Role.WEREWOLF,
        "seer": Role.SEER,
        "robber": Role.ROBBER,
        "troublemaker": Role.TROUBLEMAKER,
        "drunk": Role.DRUNK,
        "insomniac": Role.INSOMNIAC,
        "minion": Role.MINION,
        "mason": Role.MASON,
        "hunter": Role.HUNTER,
        "tanner": Role.TANNER,
        "doppelganger": Role.DOPPELGANGER,
        "doppleganger": Role.DOPPELGANGER,
        "doppelgaenger": Role.DOPPELGANGER,
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        allowed = ", ".join(role.value for role in Role)
        raise ValueError(f"unknown role {value!r}; expected one of: {allowed}") from exc


def role_team(role: Role) -> str:
    if role == Role.WEREWOLF:
        return "werewolf"
    if role == Role.MINION:
        return "minion"
    if role == Role.TANNER:
        return "tanner"
    if role in VILLAGE_ROLES:
        return "village"
    if role == Role.DOPPELGANGER:
        return "doppelganger"
    raise ValueError(f"unhandled role: {role}")
