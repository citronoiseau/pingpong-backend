from dataclasses import dataclass, field

from enum import Enum

class GameState(Enum):
    SETUP = "SETUP"
    ACTIVE = "ACTIVE"

@dataclass
class Player:
    id: str
    type: str
    name: str
    score: int

@dataclass
class Ball:
    position_x: float
    position_y: float

@dataclass
class Paddle:
    position_y: float

@dataclass
class GameStatus:
    state: str
    joined_players: list[str]
    winner: str

@dataclass
class GameInfo:
    id: str
    players: dict[str, Player] = field(default_factory=dict)
    winner: str = ""
    max_players: int = 2
    min_players: int = 2
    rounds: int = 0
    max_rounds: int = 5
    ball: Ball = field(default_factory=lambda: Ball(0, 0))  
    left_paddle: Paddle = field(default_factory=lambda: Paddle(0))  
    right_paddle: Paddle = field(default_factory=lambda: Paddle(0)) 
    isPaused: bool = False

    def get_game_state(self) -> str: 
        if len(self.players) < self.min_players:
            return GameState.SETUP.value  
        else:
            return GameState.ACTIVE.value

    def get_status(self) -> GameStatus:
        joined_players = [
            self.players[player_id].name for player_id in self.players.keys()
        ]
        return GameStatus(
            self.get_game_state(),
            joined_players,
            self.winner,
        )