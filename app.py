#!/usr/bin/env python
import base64
import logging

import numpy as np
import redis
import cv2
from flask import Flask, render_template, Response, request
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO
from engineio.payload import Payload

from models import *
from game_camera import Camera


Payload.max_decode_packets = 500


app = Flask(__name__)
socketio = SocketIO(app)


class SocketIOFilter(logging.Filter):
    def filter(self, record):
        return "socket.io" not in record.getMessage()


log = logging.getLogger('werkzeug')
log.addFilter(SocketIOFilter())

app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:admin@localhost/ElecTrap_scoreboard'
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = 'secret string'

db = SQLAlchemy(app)


r = redis.Redis(host='localhost', port=6379, decode_responses=True)


@app.route('/')
def index():
    """index page."""
    return render_template('index.html')


@app.route('/play', methods=['POST'])
def play():
    """Video streaming home page."""
    name = r.get('user_name')
    game_mode = request.form["game_mode"]
    game_body = request.form["game_body"]
    game_level = request.form["game_level"]
    entry = UserInfo(name, game_mode, game_body, game_level, 1000)
    db.session.add(entry)
    db.session.commit()
    Camera.change_game(game_mode, game_body)
    return render_template('play.html')


@app.route('/gamemode')
def gamemode():
    """ Select gamemode page."""
    return render_template('gamemode.html')


@app.route("/rank")
def rank():
    return render_template("rank.html")


@app.route('/getusername', methods=['POST'])
def getusername():
    user_name = request.form["user_name"]
    r.set('user_name', user_name)
    print(user_name)
    return render_template("gamemode.html")


def gen(camera):
    """Video streaming generator function."""
    yield b'--frame\r\n'
    while True:
        frame = camera.get_frame()
        if camera.get_game().check_gameover():
            socketio.emit('gameover', {'data': 'gameover'})
        if camera.get_game().check_outpipe():
            socketio.emit('out_pipe', {'data': 'out_pipe'})
            print("out_pipe")
        yield b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n--frame\r\n'


@app.route('/video_feed')
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(gen(Camera()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@socketio.on('image')
def image(data_image):
    encoded_data = data_image.split(',')[1]
    nparr = np.frombuffer(base64.b64decode(encoded_data), np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    Camera.set_image(img)


@socketio.on('score')
def score(form):
    result = []
    for user in UserInfo.query.filter_by(
        **form).order_by(UserInfo.score.asc()).limit(10).all():
        user_dict = vars(user)
        user_dict.pop('_sa_instance_state', None)
        result.append(user_dict)
    socketio.emit('scoreUpdate', {'data': result})


if __name__ == '__main__':
    db.create_all()
    socketio.run(app, host='0.0.0.0')
