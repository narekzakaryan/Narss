from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Set
import random


class GamePhase(Enum):
    LOBBY = auto()
    NIGHT = auto()
    DAY = auto()
    ENDED = auto()


@dataclass
class Player:
    user_id: int
    full_name: str
    is_alive: bool = True


@dataclass
class ChatGameState:
    chat_id: int
    creator_user_id: int
    players: Dict[int, Player] = field(default_factory=dict)
    phase: GamePhase = GamePhase.LOBBY
    day_number: int = 0

    mafia_ids: Set[int] = field(default_factory=set)
    detective_id: Optional[int] = None
    doctor_id: Optional[int] = None

    mafia_target: Optional[int] = None
    doctor_save: Optional[int] = None
    detective_check: Optional[int] = None

    day_votes: Dict[int, int] = field(default_factory=dict)  # voter_id -> target_id

    def reset_votes(self) -> None:
        self.day_votes.clear()

    def reset_night_actions(self) -> None:
        self.mafia_target = None
        self.doctor_save = None
        self.detective_check = None

    def add_player(self, user_id: int, full_name: str) -> bool:
        if user_id in self.players:
            return False
        self.players[user_id] = Player(user_id=user_id, full_name=full_name)
        return True

    def remove_player(self, user_id: int) -> bool:
        if user_id not in self.players:
            return False
        # Disallow removal after start
        if self.phase != GamePhase.LOBBY:
            return False
        del self.players[user_id]
        return True

    def alive_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.is_alive]

    def alive_ids(self) -> Set[int]:
        return {p.user_id for p in self.alive_players()}

    def assign_roles(self) -> None:
        player_ids = list(self.players.keys())
        random.shuffle(player_ids)

        num_players = len(player_ids)
        # Simple role formula: 1 mafia per 4 players (min 1)
        num_mafia = max(1, num_players // 4)

        self.mafia_ids = set(player_ids[:num_mafia])
        remaining = player_ids[num_mafia:]

        # Assign detective and doctor if enough players
        self.detective_id = remaining[0] if len(remaining) >= 1 else None
        self.doctor_id = remaining[1] if len(remaining) >= 2 else None

        # Start first night
        self.phase = GamePhase.NIGHT
        self.day_number = 0
        self.reset_night_actions()
        self.reset_votes()

    def role_of(self, user_id: int) -> str:
        if user_id in self.mafia_ids:
            return "Մաֆիա"
        if user_id == self.detective_id:
            return "Դետեկտիվ"
        if user_id == self.doctor_id:
            return "Բժիշկ"
        return "Քաղաքացի"

    def is_participant(self, user_id: int) -> bool:
        return user_id in self.players

    def kill_player(self, user_id: int) -> None:
        if user_id in self.players:
            self.players[user_id].is_alive = False

    def resolve_night(self) -> Dict[str, Optional[int]]:
        # Apply doctor save before mafia kill
        killed: Optional[int] = None
        saved = self.doctor_save

        if self.mafia_target is not None:
            if self.mafia_target != self.doctor_save:
                killed = self.mafia_target
                self.kill_player(killed)

        checked_role: Optional[str] = None
        if self.detective_check is not None:
            checked_role = self.role_of(self.detective_check)

        self.phase = GamePhase.DAY
        self.day_number += 1
        self.reset_votes()

        return {
            "killed_user_id": killed,
            "saved_user_id": saved,
            "checked_user_id": self.detective_check,
            "checked_role": checked_role,
        }

    def tally_day_votes(self) -> Optional[int]:
        # Count votes only from alive players
        counts: Dict[int, int] = {}
        for voter_id, target_id in self.day_votes.items():
            if voter_id in self.alive_ids() and target_id in self.alive_ids():
                counts[target_id] = counts.get(target_id, 0) + 1

        if not counts:
            return None

        # Find max; if tie, no one is eliminated
        max_votes = max(counts.values())
        top = [uid for uid, c in counts.items() if c == max_votes]
        if len(top) != 1:
            return None
        return top[0]

    def apply_day_result(self) -> Optional[int]:
        target = self.tally_day_votes()
        if target is not None:
            self.kill_player(target)
        # Move to next night if game not ended
        if self.phase != GamePhase.ENDED:
            self.phase = GamePhase.NIGHT
            self.reset_night_actions()
        return target

    def check_win(self) -> Optional[str]:
        alive_ids = self.alive_ids()
        alive_mafia = self.mafia_ids.intersection(alive_ids)
        alive_towns = alive_ids.difference(self.mafia_ids)

        if not alive_mafia:
            self.phase = GamePhase.ENDED
            return "Քաղաքացիականը հաղթեց"

        if len(alive_mafia) >= len(alive_towns):
            self.phase = GamePhase.ENDED
            return "Մաֆիան հաղթեց"

        return None