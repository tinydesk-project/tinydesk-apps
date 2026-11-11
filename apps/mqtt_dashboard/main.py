# MQTT Dashboard: tiles for MQTT topics. A tile shows the last value on its
# topic; a switch tile also sends ON / OFF, a send tile any text. The broker
# is the one in ~/mqtt.conf (the MQTT app's and `mqtt connect`'s file), the
# tiles are kept in ~/mqtt_dashboard.json.
import json
import time

import tdui
from umqtt.simple import MQTTClient

CONF = '~/mqtt.conf'
TILES = '~/mqtt_dashboard.json'
KINDS = ('value', 'switch', 'send')


def read_conf():
    """host, port, user, password and tls from ~/mqtt.conf (its own syntax:
    "key value" lines, # comments)."""
    c = {'host': '', 'port': 0, 'user': None, 'password': None, 'tls': False}
    try:
        lines = open(CONF).read().split('\n')
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if not line or line[0] == '#':
            continue
        parts = line.split(None, 1)
        key = parts[0].lower()
        val = parts[1].strip() if len(parts) > 1 else ''
        if key not in ('subscribe', 'sub', 'will_topic') and ' #' in val:
            val = val[:val.index(' #')].strip()
        if len(val) > 1 and val[0] == '"' and val[-1] == '"':
            val = val[1:-1]
        if key in ('host', 'broker', 'url'):
            for scheme in ('mqtts://', 'ssl://', 'tls://'):
                if val.startswith(scheme):
                    c['tls'] = True
                    val = val[len(scheme):]
            for scheme in ('mqtt://', 'tcp://'):
                if val.startswith(scheme):
                    val = val[len(scheme):]
            if ':' in val:
                val, port = val.rsplit(':', 1)
                c['port'] = int(port)
            elif key == 'url' or ':' in val:
                c['port'] = 0
            c['host'] = val
        elif key == 'port':
            c['port'] = int(val)
        elif key in ('username', 'user'):
            c['user'] = val
        elif key in ('password', 'pass'):
            c['password'] = val
        elif key == 'tls':
            c['tls'] = val in ('on', 'true', 'yes', '1')
    return c if c['host'] else None


def load_tiles():
    try:
        tiles = json.loads(open(TILES).read())
        return [t for t in tiles if isinstance(t, dict) and t.get('topic')][:30]
    except (OSError, ValueError):
        return []


def save_tiles():
    try:
        with open(TILES, 'w') as f:
            f.write(json.dumps([{'name': t['name'], 'topic': t['topic'], 'kind': t['kind'], 'unit': t.get('unit', '')}
                                for t in tiles]))
    except OSError as e:
        status.text = 'Could not save: %s' % e


tiles = load_tiles()
values = {}      # topic -> (text, time)
client = None
connected_to = ''

w = tdui.Window('MQTT Dashboard', 66, 20, resizable=True)
status = w.label(1, 0, 'Not connected', width=0)
lst = w.list(1, 2, 38, -3, [])
cv = w.canvas(41, 2, 24, 10)
w.label(41, 13, 'Topic:', width=0)
topic_lbl = w.label(41, 14, '', width=0)
age_lbl = w.label(41, 15, '', width=0)


def selected():
    i = lst.selected
    return tiles[i] if tiles and 0 <= i < len(tiles) else None


def row(t):
    v = values.get(t['topic'])
    text = v[0] if v else '-'
    if t['kind'] == 'switch':
        text = '[%s]' % (text if v else '?')
    elif t.get('unit') and v:
        text += ' ' + t['unit']
    return '%-16.16s %s' % (t['name'], text[:20])


def show_list():
    keep = lst.selected
    lst.items = [row(t) for t in tiles] or ['(no tiles: press Add)']
    if tiles and 0 <= keep < len(tiles):
        lst.selected = keep


def show_tile(lst_=None):
    t = selected()
    cv.clear()
    if not t:
        topic_lbl.text = age_lbl.text = ''
        return
    v = values.get(t['topic'])
    cv.put(0, 0, t['name'][:24], 15)
    text = v[0] if v else '--'
    try:
        float(text)
        numeric = len(text) <= 6
    except ValueError:
        numeric = text.upper() in ('ON', 'OFF') and len(text) <= 6
    if numeric:
        colour = 46 if text.upper() == 'ON' else (244 if text.upper() == 'OFF' else 51)
        cv.big(0, 2, text, colour, -1, scale=1, width=0)
        if t.get('unit'):
            cv.put(0, 6, t['unit'][:24], 250)
    else:
        for i in range(0, min(len(text), 24 * 7), 24):
            cv.put(0, 2 + i // 24, text[i:i + 24], 250)
    topic_lbl.text = t['topic'][:63]
    age_lbl.text = ('%d s ago' % (time.time() - v[1])) if v else 'no message yet'


def on_message(topic, msg):
    topic = topic.decode() if isinstance(topic, bytes) else topic
    try:
        text = msg.decode()
    except UnicodeError:
        text = '%d bytes' % len(msg)
    text = text.strip().replace('\n', ' ')
    for t in tiles:
        if t['topic'] == topic or match(t['topic'], topic):
            values[t['topic']] = (text, time.time())
    show_list()
    show_tile()


def match(pattern, topic):
    p, t = pattern.split('/'), topic.split('/')
    for i, part in enumerate(p):
        if part == '#':
            return True
        if i >= len(t) or (part != '+' and part != t[i]):
            return False
    return len(p) == len(t)


def connect(button=None):
    global client, connected_to
    disconnect()
    c = read_conf()
    if not c:
        status.text = 'No broker in ~/mqtt.conf: press Connect to see how to set one'
        if button:
            tdui.msgbox('MQTT Dashboard', 'No broker in ~/mqtt.conf.\n'
                        'Set one with the MQTT app (Config...)\nor run: mqtt config init')
        return
    status.text = 'Connecting to %s ...' % c['host']
    tdui.poll()
    ssl = None
    if c['tls']:
        import ssl as ssl_mod
        ssl = ssl_mod.SSLContext(ssl_mod.PROTOCOL_TLS_CLIENT)
    port = c['port'] or (8883 if c['tls'] else 1883)
    try:
        cl = MQTTClient('tinydesk-dash-%d' % (time.ticks_ms() & 0xFFFFFF), c['host'], port,
                        c['user'], c['password'], keepalive=60, ssl=ssl)
        cl.set_callback(on_message)
        cl.connect()
        for topic in set(t['topic'] for t in tiles):
            cl.subscribe(topic)
    except Exception as e:
        status.text = 'Not connected: %s' % e
        return
    client = cl
    connected_to = '%s:%d' % (c['host'], port)
    status.text = 'Connected to ' + connected_to


def disconnect():
    global client
    if client:
        try:
            client.disconnect()
        except Exception:
            pass
    client = None


last_ping = [time.time()]


def tick():
    global client
    if not client:
        return
    try:
        client.check_msg()
        if time.time() - last_ping[0] >= 30:
            client.ping()
            last_ping[0] = time.time()
    except Exception as e:
        client = None
        status.text = 'Connection lost (%s): press Connect' % e
    show_tile()


def add(_):
    name = tdui.inputbox('Add a tile', 'Name:')
    if not name:
        return
    topic = tdui.inputbox('Add a tile', 'Topic (+ and # allowed):')
    if not topic:
        return
    k = tdui.msgbox('Add a tile', 'What kind of tile?\nValue: shows the topic\n'
                    'Switch: shows it, sends ON / OFF\nSend: shows it, sends text', 'Value|Switch|Send')
    if k < 0:
        return
    unit = ''
    if k == 0:
        unit = tdui.inputbox('Add a tile', 'Unit (optional, e.g. C or %):') or ''
    tiles.append({'name': name[:16], 'topic': topic.strip(), 'kind': KINDS[k], 'unit': unit[:8]})
    save_tiles()
    if client:
        try:
            client.subscribe(topic.strip())
        except Exception as e:
            status.text = 'Subscribe failed: %s' % e
    show_list()
    lst.selected = len(tiles) - 1
    show_tile()


def remove(_):
    t = selected()
    if t and tdui.confirm('Remove a tile', 'Remove "%s"?' % t['name']):
        tiles.remove(t)
        save_tiles()
        show_list()
        show_tile()


def send(_=None):
    t = selected()
    if not t:
        return
    if t['kind'] == 'value' or '+' in t['topic'] or '#' in t['topic']:
        tdui.msgbox('MQTT Dashboard', 'This tile only shows its topic.')
        return
    if not client:
        tdui.msgbox('MQTT Dashboard', 'Not connected.')
        return
    if t['kind'] == 'switch':
        v = values.get(t['topic'])
        payload = 'OFF' if v and v[0].upper() == 'ON' else 'ON'
    else:
        payload = tdui.inputbox('Send', 'Text to send on %s:' % t['topic'][:40])
        if payload is None:
            return
    try:
        client.publish(t['topic'], payload, retain=t['kind'] == 'switch')
        status.text = 'Sent %s to %s' % (payload[:20], t['topic'][:30])
    except Exception as e:
        status.text = 'Send failed: %s' % e


lst.on_select = show_tile
lst.on_activate = send
w.button(1, -1, 'Connect', connect)
w.button(13, -1, 'Add', add)
w.button(21, -1, 'Remove', remove)
w.button(32, -1, 'Toggle/Send', send)


def closed(win):
    disconnect()


w.on_close = closed
show_list()
show_tile()
w.every(200, tick)
connect()
tdui.run()
disconnect()
