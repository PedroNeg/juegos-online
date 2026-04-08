from flask import Flask, render_template, request
from flask_socketio import SocketIO, join_room, emit
import random, string

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
    join_room(code)
    p0name = room["names"][room["players"][0]]
    emit("game_start", {
        "game": room["game"], "code": code,
        "symbol": "O", "myName": name, "oppName": p0name,
        "board": room["board"], "myTurn": False,
    })
    emit("game_start", {
        "game": room["game"], "code": code,
        "symbol": "X", "myName": p0name, "oppName": name,
        "board": room["board"], "myTurn": True,
    }, to=room["players"][0])

@socketio.on("move")
def on_move(data):
    code = data.get("code")
    if code not in rooms:
        return
    room = rooms[code]
    if not room["active"] or request.sid != room["players"][room["turn"]]:
        return
    game = room["game"]
    symbol = "X" if room["turn"] == 0 else "O"
    result = None

    if game == "tateti":
        idx = data.get("idx")
        if room["board"][idx] != "":
            return
        room["board"][idx] = symbol
        combo = check_tateti(room["board"])
        draw = all(c != "" for c in room["board"])
        if combo:
            result = {"winner": symbol, "combo": combo}
            room["active"] = False
        elif draw:
            result = {"winner": "draw"}
            room["active"] = False
    else:
        col = data.get("col")
        row = drop_piece(room["board"], col)
        if row is None:
            return
        room["board"][row][col] = symbol
        cells = check_connect4(room["board"], row, col, symbol)
        draw = all(room["board"][0][c] != "" for c in range(7))
        if cells:
            result = {"winner": symbol, "cells": cells}
            room["active"] = False
        elif draw:
            result = {"winner": "draw"}
            room["active"] = False

    room["turn"] = 1 - room["turn"]
    opp_idx = 1 - room["players"].index(request.sid)
    opp = room["players"][opp_idx]
    emit("board_update", {"board": room["board"], "myTurn": False, "result": result}, to=request.sid)
    emit("board_update", {"board": room["board"], "myTurn": True,  "result": result}, to=opp)

@socketio.on("rematch")
def on_rematch(data):
    code = data.get("code")
    if code not in rooms:
        return
    room = rooms[code]
    room["board"] = empty_board(room["game"])
    room["turn"] = 0
    room["active"] = True
    emit("rematch_start", {"board": room["board"], "myTurn": True},  to=room["players"][0])
    if len(room["players"]) > 1:
        emit("rematch_start", {"board": room["board"], "myTurn": False}, to=room["players"][1])

@socketio.on("disconnect")
def on_disconnect():
    for code, room in list(rooms.items()):
        if request.sid in room["players"]:
            emit("opponent_left", {}, to=code)
            del rooms[code]
            break

TATETI_WINS = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]

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
    directions = [(0,1),(1,0),(1,1),(1,-1)]
    for dr, dc in directions:
        cells = [(row, col)]
        for sign in (1, -1):
            r, c = row + dr*sign, col + dc*sign
            while 0 <= r < 6 and 0 <= c < 7 and board[r][c] == sym:
                cells.append((r, c))
                r += dr*sign
                c += dc*sign
        if len(cells) >= 4:
            return [[r, c] for r, c in cells]
    return None

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
