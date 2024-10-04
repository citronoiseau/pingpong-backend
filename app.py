import eventlet
eventlet.monkey_patch()  # noqa: E402 - Required to run before other imports

from flask import Flask, request
from flask_socketio import SocketIO, emit, disconnect
from flask_cors import CORS
from flask_caching import Cache
from data.gameInfo import Player, GameInfo
from random import randint
from uuid import uuid4
from dataclasses import asdict
import time
import msgpack

last_emit_time_left = time.time()
last_emit_time_right = time.time()

async_mode = 'eventlet'

test_game_id = "aaa-aaa-aaa"
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, async_mode=async_mode, cors_allowed_origins="*",  compression=True,  binary=True )


config = {
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 3600,  # in seconds, keep a game around for one hour
}


# tell Flask to use the above defined config
app.config.from_mapping(config)
game_cache = Cache(app)


def rand_xyz() -> str:
    a, z = ord("a"), ord("z")
    return "".join(chr(randint(a, z)) for _ in range(0, 3))


def test_uuid(ch: str) -> str:
    return f"{ch * 8}-{ch * 4}-{ch * 4}-{ch * 4}-{ch * 12}"

@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


@app.route("/new_game")
def new_game():
    id = test_game_id  # test id
    while id and game_cache.has(id):
        id = f"{rand_xyz()}-{rand_xyz()}-{rand_xyz()}"
    game = GameInfo(id)
    player1_id = test_uuid("a") if game.id == test_game_id else str(uuid4())
    player1 = Player(player1_id, "host", "Player 1", 0)
    game.players[player1.id] = player1
    game_cache.set(id, game)
    return {"id": id, "player": player1}


@app.route("/join_game/<id>")
def join_game(id: str):
    if not game_cache.has(id):
        raise RuntimeError(f"Game {id} does not exists.")
    game: GameInfo = game_cache.get(id)
    if len(game.players) == game.max_players:
        raise RuntimeError(f"Game {id} is full.")
    player2_id = test_uuid("b") if game.id == test_game_id else str(uuid4())
    player2 = Player(player2_id, "guest", "Player 2", 0)
    game.players[player2.id] = player2
    game_cache.set(id, game)
    return {"id": id, "player": player2}


@app.route("/status/<id>")
def status(id: str):
    if not game_cache.has(id):
        raise RuntimeError(f"Game {id} does not exists.")
    return asdict(game_cache.get(id).get_status())


@socketio.on('connect')
def handle_connect():
    id = request.args.get('id')  
    if not id or not game_cache.has(id):
        print(f"Game ID {id} is invalid or missing.")
        disconnect()  
    else:
        print(f"Player connected to game {id}")



@socketio.on('leaveGame')
def handle_disconnect():
        emit("game_result", broadcast=True)


@socketio.on("update_game_state_left")
def handle_left_player_update(data):
    global last_emit_time_left
    current_time = time.time()
    

    if current_time - last_emit_time_left > 1/60: 
        last_emit_time_left = current_time
        eventlet.sleep(0)  # Yield control to the event loop
        
        id = request.args.get('id')  
        paddle_data = data["paddle"] 
        ball_data = data["ball"] 
        
        game: GameInfo = game_cache.get(id)
        if game:
            # Compare new data with the current game state
            is_ball_updated = (
                game.ball.position_x != ball_data["position_x"] or
                game.ball.position_y != ball_data["position_y"]
            )
            is_left_paddle_updated = game.left_paddle != paddle_data["position"]
            is_score_updated = (
                game.players[list(game.players.keys())[0]].score != data["scores"][0] or
                game.players[list(game.players.keys())[1]].score != data["scores"][1]
            )

            # Update game state
            game.left_paddle = paddle_data["position"]  
            game.ball.position_x = ball_data["position_x"] 
            game.ball.position_y = ball_data["position_y"]
            game.rounds = data["rounds"]
            game.max_rounds = data.get("max_rounds", game.max_rounds)
            game.players[list(game.players.keys())[0]].score = data["scores"][0]  
            game.players[list(game.players.keys())[1]].score = data["scores"][1]
            game.winner = data.get("winner", game.winner)

            # Emit update only if something has changed
        if is_ball_updated or is_left_paddle_updated or is_score_updated:
                game_state = {
                    "ball": {
                        "position_x": game.ball.position_x,
                        "position_y": game.ball.position_y
                    },
                    "left_paddle": game.left_paddle,
                    "scores": [
                        game.players[list(game.players.keys())[0]].score,
                        game.players[list(game.players.keys())[1]].score
                    ],
                    "rounds": game.rounds,
                    "winner": game.winner,
                    "max_rounds": game.max_rounds,
                }
                # Use binary serialization for faster transmission
                try:
                    packed_data = msgpack.packb(game_state)
                    emit("game_state_updated", packed_data, broadcast=True)
                except Exception as e:
                    print(f"Error encoding game state: {e}")


@socketio.on("update_game_state_right")
def handle_right_player_update(data):
    global last_emit_time_right
    current_time = time.time()


    if current_time - last_emit_time_right > 1/60:  
        last_emit_time_right = current_time
        eventlet.sleep(0)  # Yield control to the event loop
        
        id = request.args.get('id')  
        paddle_data = data["paddle"]  

        game: GameInfo = game_cache.get(id)
        if game:
            # Compare new paddle position with the current one
            is_right_paddle_updated = game.right_paddle != paddle_data["position"]

            # Update the game state
            game.right_paddle = paddle_data["position"]

            # Emit update only if the right paddle has changed
            if is_right_paddle_updated:
                try:
                    packed_data = msgpack.packb({"right_paddle": game.right_paddle})
                    emit("game_state_updated", packed_data, broadcast=True)
                except Exception as e:
                    print(f"Error encoding game state for right paddle: {e}")


@socketio.on("game_pause_updated")
def handle_board_pause(data):
    id = request.args.get('id') 
    isPaused = data["isPaused"]

    game: GameInfo = game_cache.get(id)
    if game:
        game.isPaused = isPaused
        
        emit("game_pause_updated", {
            "isPaused": game.isPaused
        }, broadcast=True)


if __name__ == "__main__":
        socketio.run(app, debug=True, host='0.0.0.0', port=5000)
