from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import random
import string
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "tateti-cuatro-secret-2024"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

rooms = {}


def make_code():
    while True:
        code = "".join(random.choices(string.ascii_uppercase, k=4))
        if code not in rooms:
            return code


def empty_board(game):
    if game == "tateti":
        return [""] * 9
    return [[""] * 7 for _ in range(6)]


def player_symbol(player_index):
    return "X" if player_index == 0 else "O"


def other_index(player_index):
    return 1 - player_index


TATETI_WINS = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6)
]


def check_tateti(board):
    for a, b, c in TATETI_WINS:
        if board[a] and board[a] == board[b] == board[c]:
            return [a, b, c]
    return None


def drop_piece(board, col):
    for row in range(5, -1, -1):
        if board[row][col] == "":
            return row
    return None


def check_connect4(board, row, col, sym):
    directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
    for dr, dc in directions:
        cells = [(row, col)]
        for sign in (1, -1):
            r, c = row + dr * sign, col + dc * sign
            while 0 <= r < 6 and 0 <= c < 7 and board[r][c] == sym:
                cells.append((r, c))
                r += dr * sign
                c += dc * sign
        if len(cells) >= 4:
            return [[r, c] for r, c in cells]
    return None


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("create_room")
def on_create(data):
    game = data.get("game", "tateti")
    name = data.get("name", "Jugador 1")[:20]
    code = make_code()
    rooms[code] = {
        "game": game,
        "players": [request.sid],
        "names": {request.sid: name},
        "board": empty_board(game),
        "turn": 0,
        "starter": 0,
        "active": False,
    }
    join_room(code)
    emit("room_created", {"code": code, "game": game, "name": name})


@socketio.on("join_room_req")
def on_join(data):
    code = data.get("code", "").upper().strip()
    name = data.get("name", "Jugador 2")[:20]
    if code not in rooms:
        emit("error", {"msg": "Sala no encontrada."})
        return
    room = rooms[code]
    if len(room["players"]) >= 2:
        emit("error", {"msg": "La sala ya esta llena."})
        return
    room["players"].append(request.sid)
    room["names"][request.sid] = name
    room["active"] = True
    room["turn"] = room["starter"]
    join_room(code)
    p0_sid = room["players"][0]
    p1_sid = room["players"][1]
    p0_name = room["names"][p0_sid]
    p1_name = room["names"][p1_sid]
    emit("game_start", {
        "game": room["game"], "code": code, "symbol": "O",
        "myName": p1_name, "oppName": p0_name,
        "board": room["board"], "myTurn": room["turn"] == 1,
    }, to=p1_sid)
    emit("game_start", {
        "game": room["game"], "code": code, "symbol": "X",
        "myName": p0_name, "oppName": p1_name,
        "board": room["board"], "myTurn": room["turn"] == 0,
    }, to=p0_sid)


@socketio.on("move")
def on_move(data):
    code = data.get("code")
    if code not in rooms:
        return
    room = rooms[code]
    if not room["active"] or len(room["players"]) < 2:
        return
    current_idx = room["turn"]
    current_sid = room["players"][current_idx]
    if request.sid != current_sid:
        return
    game = room["game"]
    symbol = player_symbol(current_idx)
    result = None
    if game == "tateti":
        idx = data.get("idx")
        if not isinstance(idx, int) or not (0 <= idx < 9):
            return
        if room["board"][idx] != "":
            return
        room["board"][idx] = symbol
        combo = check_tateti(room["board"])
        draw = all(cell != "" for cell in room["board"])
        if combo:
            result = {"winner": symbol, "combo": combo}
        elif draw:
            result = {"winner": "draw"}
    else:
        col = data.get("col")
        if not isinstance(col, int) or not (0 <= col < 7):
            return
        row = drop_piece(room["board"], col)
        if row is None:
            return
        room["board"][row][col] = symbol
        cells = check_connect4(room["board"], row, col, symbol)
        draw = all(room["board"][0][c] != "" for c in range(7))
        if cells:
            result = {"winner": symbol, "cells": cells}
        elif draw:
            result = {"winner": "draw"}
    opponent_idx = other_index(current_idx)
    opponent_sid = room["players"][opponent_idx]
    if result:
        room["active"] = False
        if result["winner"] == "draw":
            room["starter"] = other_index(room["starter"])
        else:
            room["starter"] = opponent_idx
        result["nextStarter"] = player_symbol(room["starter"])
        emit("board_update", {"board": room["board"], "myTurn": False, "result": result}, to=current_sid)
        emit("board_update", {"board": room["board"], "myTurn": False, "result": result}, to=opponent_sid)
    else:
        room["turn"] = opponent_idx
        emit("board_update", {"board": room["board"], "myTurn": False, "result": None}, to=current_sid)
        emit("board_update", {"board": room["board"], "myTurn": True,  "result": None}, to=opponent_sid)


@socketio.on("rematch")
def on_rematch(data):
    code = data.get("code")
    if code not in rooms:
        return
    room = rooms[code]
    if len(room["players"]) < 2:
        return
    room["board"] = empty_board(room["game"])
    room["turn"] = room["starter"]
    room["active"] = True
    p0_sid = room["players"][0]
    p1_sid = room["players"][1]
    emit("rematch_start", {"board": room["board"], "myTurn": room["turn"] == 0, "starter": player_symbol(room["starter"])}, to=p0_sid)
    emit("rematch_start", {"board": room["board"], "myTurn": room["turn"] == 1, "starter": player_symbol(room["starter"])}, to=p1_sid)


# ── CHAT ──────────────────────────────────────────────────────────────────────

@socketio.on("chat_msg")
def on_chat(data):
    code = data.get("code")
    text = data.get("text", "").strip()[:200]
    if not text or code not in rooms:
        return
    room = rooms[code]
    if request.sid not in room["players"]:
        return
    name = room["names"].get(request.sid, "?")
    socketio.emit("chat_msg", {"name": name, "text": text}, to=code)


@socketio.on("disconnect")
def on_disconnect():
    for code, room in list(rooms.items()):
        if request.sid in room["players"]:
            emit("opponent_left", {}, to=code)
            del rooms[code]
            break


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True
    )
