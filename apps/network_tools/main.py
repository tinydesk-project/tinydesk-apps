# Network Tools: scan for Wi-Fi networks, show the board's access point with
# a QR code phones can scan to join it, ping a host and check a TCP port.
import socket
import time

import tdui
import tinydesk

import qr

TMP = '~/.network_tools.txt'


def run(cmd):
    """Run a shell command and return its output lines."""
    tinydesk.shell('%s > %s' % (cmd, TMP))
    try:
        with open(TMP) as f:
            out = f.read()
    except OSError:
        out = ''
    return [line.rstrip() for line in out.split('\n') if line.strip()]


w = tdui.Window('Network Tools', 66, 20, resizable=True)
pages = {}
current = ['']


def page(name, widget):
    pages.setdefault(name, []).append(widget)
    widget.visible = False
    return widget


def go(name):
    current[0] = name
    for n, ws in pages.items():
        for x in ws:
            x.visible = n == name
    if name == 'ap':
        show_ap()


tabs = (('Wi-Fi scan', 'scan'), ('Access point', 'ap'), ('Ping', 'ping'), ('Port check', 'port'))
x = 1
for label, name in tabs:
    w.button(x, 0, label, lambda b, n=name: go(n))
    x += len(label) + 5

# Wi-Fi scan
scan_info = page('scan', w.label(1, 2, 'Press Scan to look for networks.', width=0))
scan_list = page('scan', w.list(1, 3, -1, -3, []))


def scan(_):
    scan_info.text = 'Scanning ...'
    tdui.poll(50)
    nets = []
    for line in run('wifiscan'):
        parts = line.split()
        if len(parts) < 4 or not parts[0].isdigit():
            continue
        # "#  SSID  RSSI  CH  AUTH": the SSID may have spaces, AUTH is last.
        auth, rest = parts[-1], line.split(None, 1)[1].rstrip()
        rest = rest[:len(rest) - len(auth)].rstrip()
        bits = rest.rsplit(None, 2)
        if len(bits) < 3:
            continue
        ssid, rssi, ch = bits[0].strip() or '(hidden)', int(bits[1]), bits[2]
        nets.append((rssi, ssid, ch, auth))
    nets.sort(reverse=True)
    scan_list.items = ['%-24.24s %4d dBm %s ch %-3s %s' % (s, r, bars(r), c, a) for r, s, c, a in nets] or \
        ['(no networks found)']
    scan_info.text = '%d network%s, strongest first' % (len(nets), '' if len(nets) == 1 else 's')


def bars(rssi):
    n = 4 if rssi >= -55 else 3 if rssi >= -67 else 2 if rssi >= -75 else 1 if rssi >= -85 else 0
    return '#' * n + '.' * (4 - n)


page('scan', w.button(1, -1, 'Scan', scan))

# Access point
ap_lines = [page('ap', w.label(1, 2 + i, '', width=0)) for i in range(5)]
ap = {}


def show_ap():
    ap.clear()
    lines = run('wifiap status')
    for line in lines:
        s = line.strip()
        if s.startswith('Access point:'):
            ap['state'] = s.split(':', 1)[1].strip()
        elif ':' in s:
            k, v = s.split(':', 1)
            ap[k.strip()] = v.strip()
    if 'state' not in ap:
        ap_lines[0].text = 'This board has no access point settings.'
        for lbl in ap_lines[1:]:
            lbl.text = ''
        return
    ap_lines[0].text = 'State:     ' + ap['state']
    ap_lines[1].text = 'Name:      ' + ap.get('name', '')
    ap_lines[2].text = 'Password:  ' + ap.get('password', '')
    ap_lines[3].text = 'Address:   ' + ap.get('address', '-')
    ap_lines[4].text = 'Show QR opens a code phones scan to join it.'


def ap_mode(mode):
    def do(_):
        run('wifiap ' + mode)
        time.sleep_ms(1200)
        show_ap()
    return do


def escape(s):
    for ch in '\\;,":':
        s = s.replace(ch, '\\' + ch)
    return s


def show_qr(_):
    if not ap.get('name'):
        show_ap()
    if not ap.get('name'):
        return
    text = 'WIFI:T:WPA;S:%s;P:%s;;' % (escape(ap['name']), escape(ap.get('password', '')))
    try:
        m = qr.encode(text)
    except ValueError as e:
        tdui.msgbox('QR code', str(e))
        return
    n = len(m) + 2   # a quiet zone of one module
    cols, rows = n, (n + 1) // 2
    win = tdui.Window('Join ' + ap['name'][:24], max(cols, 26), rows + 1)
    cv = win.canvas(0, 0, cols, rows)

    def dark(r, c):
        return 0 < r < n - 1 and 0 < c < n - 1 and m[r - 1][c - 1]

    with tdui.batch():
        for y in range(rows):
            line = ''
            for c in range(n):
                top, bottom = dark(2 * y, c), dark(2 * y + 1, c)
                line += '█' if top and bottom else '▀' if top else '▄' if bottom else ' '
            cv.put(0, y, line, 16, 231)
    win.label(0, rows, 'Scan with a phone camera', width=0)


page('ap', w.button(1, -1, 'Show QR', show_qr))
page('ap', w.button(13, -1, 'On', ap_mode('on')))
page('ap', w.button(20, -1, 'Off', ap_mode('off')))
page('ap', w.button(28, -1, 'Auto', ap_mode('auto')))
page('ap', w.button(37, -1, 'Refresh', lambda b: show_ap()))

# Ping
page('ping', w.label(1, 2, 'Host:', width=6))
ping_host = page('ping', w.textbox(7, 2, 30, 'pool.ntp.org'))
ping_out = page('ping', w.list(1, 4, -1, -3, []))


def ping(_=None):
    host = ping_host.text.strip()
    if not host:
        return
    ping_out.items = ['Pinging %s ...' % host]
    tdui.poll(50)
    ping_out.items = run('ping -c 4 ' + host.split()[0]) or ['(no answer)']


ping_host.on_enter = ping
page('ping', w.button(1, -1, 'Ping', ping))

# Port check
page('port', w.label(1, 2, 'Host:', width=6))
port_host = page('port', w.textbox(7, 2, 30, ''))
page('port', w.label(39, 2, 'Port:', width=6))
port_num = page('port', w.textbox(45, 2, 7, '80'))
port_out = page('port', w.list(1, 4, -1, -3, []))


def check(_=None):
    host = port_host.text.strip()
    try:
        port = int(port_num.text)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        tdui.msgbox('Port check', 'The port is 1 to 65535.')
        return
    if not host:
        return
    port_out.append('%s:%d ...' % (host, port))
    tdui.poll(50)
    t0 = time.ticks_ms()
    s = None
    try:
        addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0][-1]
        s = socket.socket()
        s.settimeout(5)
        s.connect(addr)
        result = 'open (%d ms)' % time.ticks_diff(time.ticks_ms(), t0)
    except OSError as e:
        result = 'closed or unreachable (%s)' % e
    finally:
        if s:
            s.close()
    items = port_out.items
    items[-1] = '%s:%d  %s' % (host, port, result)
    port_out.items = items[-200:]


port_host.on_enter = check
port_num.on_enter = check
page('port', w.button(1, -1, 'Check', check))

go('scan')
tdui.run()
