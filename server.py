# all_in_one_server.py (With Analog Stick Keybinding)
import socket, qrcode, base64, threading, webview, sys
from io import BytesIO
from flask import Flask, render_template, request
from flask_socketio import SocketIO
from pynput.keyboard import Controller, Key

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a-very-secret-key'
socketio = SocketIO(app)
keyboard = Controller()

players = {}
MAX_PLAYERS = 5
PLAYER_MAPS = {}
joystick_key_state = {}

# --- UPDATED: Default map now includes analog stick directions ---
def get_default_map():
    return {
        'A': 'x', 'B': ' ', 'X': 'c', 'Y': 'z',
        'DPAD_UP': 'ArrowUp', 'DPAD_DOWN': 'ArrowDown',
        'DPAD_LEFT': 'ArrowLeft', 'DPAD_RIGHT': 'ArrowRight',
        'LSHLDR': 'q', 'RSHLDR': 'e',
        'L2': 'f', 'R2': 'g',
        'VIEW': '1', 'MENU': '2',
        'LEFT_STICK_UP': 'w',
        'LEFT_STICK_DOWN': 's',
        'LEFT_STICK_LEFT': 'a',
        'LEFT_STICK_RIGHT': 'd',
        'RIGHT_STICK_UP': 'ArrowUp',
        'RIGHT_STICK_DOWN': 'ArrowDown',
        'RIGHT_STICK_LEFT': 'ArrowLeft',
        'RIGHT_STICK_RIGHT': 'ArrowRight',
    }
for i in range(1, MAX_PLAYERS + 1):
    PLAYER_MAPS[i] = get_default_map()

SPECIAL_KEYS = {
    ' ': Key.space, 'ArrowUp': Key.up, 'ArrowDown': Key.down, 'ArrowLeft': Key.left,
    'ArrowRight': Key.right, 'Enter': Key.enter, 'Escape': Key.esc,
    'Shift': Key.shift, 'Control': Key.ctrl, 'Alt': Key.alt,
}

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('10.255.255.255', 1)); IP = s.getsockname()[0]; s.close(); return IP
def generate_qr_code(url):
    qr = qrcode.QRCode(version=1, box_size=10, border=4); qr.add_data(url); qr.make(fit=True); img = qr.make_image(fill_color="black", back_color="white"); buffered = BytesIO(); img.save(buffered, format="PNG"); return f"data:image/png;base64,{base64.b64encode(buffered.getvalue()).decode('utf-8')}"

@app.route('/')
def index(): return render_template('gamepad.html')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

def broadcast_dashboard_update():
    player_ids = list(players.keys())
    socketio.emit('dashboard_update', {'players': player_ids})

@socketio.on('connect')
def handle_connect():
    if request.referrer and '/dashboard' in request.referrer:
        print("🖥️  Dashboard UI connected.")
        server_url = f"http://{get_local_ip()}:{port}"
        qr_code_data = generate_qr_code(server_url)
        socketio.emit('initial_data', {'qr_code': qr_code_data, 'server_url': server_url}, room=request.sid)
        broadcast_dashboard_update()
    else:
        if len(players) >= MAX_PLAYERS: return False
        player_id = next((i for i in range(1, MAX_PLAYERS + 2) if i not in players), None)
        players[player_id] = request.sid
        socketio.emit('assign_id', {'playerId': player_id}, room=request.sid)
        print(f"✔️ Player {player_id} connected."); broadcast_dashboard_update()

@socketio.on('disconnect')
def handle_disconnect():
    player_id_to_remove = next((pid for pid, sid in players.items() if sid == request.sid), None)
    if player_id_to_remove:
        del players[player_id_to_remove]
        print(f"❌ Player {player_id_to_remove} disconnected."); broadcast_dashboard_update()

@socketio.on('gamepad_event')
def handle_gamepad_event(data):
    player_id = next((pid for pid, sid in players.items() if sid == request.sid), None)
    if not player_id: return
    button_name, action = data.get('button'), data.get('action')
    key_string = PLAYER_MAPS[player_id].get(button_name)
    if key_string:
        key_to_press = SPECIAL_KEYS.get(key_string, key_string)
        if action == 'press': keyboard.press(key_to_press)
        elif action == 'release': keyboard.release(key_to_press)

def update_key_state(key, should_be_pressed):
    key_obj = SPECIAL_KEYS.get(key, key)
    state_key = (request.sid, key) # Unique key per player session and key
    current_state = joystick_key_state.get(state_key, False)
    if should_be_pressed and not current_state:
        keyboard.press(key_obj)
        joystick_key_state[state_key] = True
    elif not should_be_pressed and current_state:
        keyboard.release(key_obj)
        joystick_key_state[state_key] = False

# --- UPDATED: Joystick handler now uses the editable player map ---
@socketio.on('joystick_move')
def handle_joystick_move(data):
    player_id = next((pid for pid, sid in players.items() if sid == request.sid), None)
    if not player_id: return
    
    player_map = PLAYER_MAPS.get(player_id, {})
    stick, x_val, y_val = data.get('stick'), data.get('x', 0.0), data.get('y', 0.0)
    threshold = 0.5

    if stick == 'left-stick':
        update_key_state(player_map['LEFT_STICK_UP'], y_val > threshold)
        update_key_state(player_map['LEFT_STICK_DOWN'], y_val < -threshold)
        update_key_state(player_map['LEFT_STICK_LEFT'], x_val < -threshold)
        update_key_state(player_map['LEFT_STICK_RIGHT'], x_val > threshold)
    elif stick == 'right-stick':
        update_key_state(player_map['RIGHT_STICK_UP'], y_val > threshold)
        update_key_state(player_map['RIGHT_STICK_DOWN'], y_val < -threshold)
        update_key_state(player_map['RIGHT_STICK_LEFT'], x_val < -threshold)
        update_key_state(player_map['RIGHT_STICK_RIGHT'], x_val > threshold)

@socketio.on('get_mappings')
def handle_get_mappings(): socketio.emit('mappings_updated', PLAYER_MAPS, room=request.sid)

@socketio.on('update_mapping')
def handle_update_mapping(data):
    player_id, button, new_key = int(data.get('player_id')), data.get('button'), data.get('new_key')
    if player_id in PLAYER_MAPS and button in PLAYER_MAPS[player_id]:
        PLAYER_MAPS[player_id][button] = new_key
        print(f"🔄 Player {player_id} keybinding updated: {button} is now '{new_key}'")
        socketio.emit('mappings_updated', PLAYER_MAPS)

if __name__ == '__main__':
    port = 8000; host_ip = get_local_ip(); dashboard_url = f"http://127.0.0.1:{port}/dashboard"
    server_thread = threading.Thread(target=lambda: socketio.run(app, host='0.0.0.0', port=port), daemon=True)
    server_thread.start()
    print("="*60 + f"\n🚀 Server running at http://{host_ip}:{port}\n" + "🖥️  Dashboard is popping up in a new window...\n" + "="*60)
    webview.create_window('Gamepad Server Dashboard', dashboard_url, width=900, height=700)
    webview.start()