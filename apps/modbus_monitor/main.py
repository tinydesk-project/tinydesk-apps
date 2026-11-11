# Modbus Monitor: watch up to 8 Modbus values (TCP or RTU) with bars and a
# trend of the selected one, write a value, and log them all to a CSV file
# (on the SD card when there is one). Points are kept in
# ~/modbus_monitor.json.
import json
import os
import time

import tdui
import tinydesk

CONF = '~/modbus_monitor.json'
MAX_POINTS = 8
TREND = 40
TABLES = ('hr', 'ir', 'co', 'di')


def load():
    try:
        c = json.loads(open(CONF).read())
        return c.get('points', [])[:MAX_POINTS], max(1, int(c.get('every', 2)))
    except (OSError, ValueError, TypeError):
        return [], 2


def save():
    try:
        with open(CONF, 'w') as f:
            f.write(json.dumps({'points': points, 'every': every[0]}))
    except OSError as e:
        status.text = 'Could not save: %s' % e


points, every_s = load()
every = [every_s]
values = [None] * MAX_POINTS
history = [[] for _ in range(MAX_POINTS)]
log_file = [None]

w = tdui.Window('Modbus Monitor', 70, 21, resizable=True)
status = w.label(1, 0, '', width=0)
lst = w.list(1, 2, 44, 10, [])
cv = w.canvas(47, 2, 22, 10)
trend = w.canvas(1, 13, 68, 5)


def point_name(p):
    return '%s %s %s:%d' % (p['target'], p['unit'], p['table'], p['addr'])


def scaled(p, raw):
    return raw * p.get('scale', 1.0) + p.get('offset', 0.0)


def fmt(p, v):
    if v is None:
        return '--'
    if p['table'] in ('co', 'di'):
        return 'ON' if v else 'OFF'
    s = p.get('scale', 1.0)
    return ('%d' % v) if s == int(s) and p.get('offset', 0.0) == int(p.get('offset', 0.0)) else ('%.2f' % v)


def row(i, p):
    v = values[i]
    text = fmt(p, v) + (' ' + p.get('units', '') if v is not None and p.get('units') else '')
    return '%-14.14s %12s  %s' % (p['name'], text[:12], 'err' if v is None and p.get('_err') else '')


def show_list():
    keep = lst.selected
    lst.items = [row(i, p) for i, p in enumerate(points)] or ['(no points: press Add)']
    if points and 0 <= keep < len(points):
        lst.selected = keep


def bar_of(i, p):
    v = values[i]
    lo, hi = p.get('min', 0.0), p.get('max', 100.0)
    if v is None or hi <= lo:
        return 0
    return max(0, min(100, int((v - lo) * 100 / (hi - lo))))


def show_bars():
    with tdui.batch():
        cv.clear()
        for i, p in enumerate(points):
            n = bar_of(i, p) * 14 // 100
            cv.put(0, i, '%-6.6s' % p['name'], 250)
            cv.put(7, i, '#' * n, 46 if values[i] is not None else 244)
            cv.put(7 + n, i, '.' * (14 - n), 238)


def show_trend():
    i = lst.selected
    with tdui.batch():
        trend.clear()
        if not points or not 0 <= i < len(points):
            return
        p = points[i]
        h = history[i]
        nums = [v for v in h if v is not None]
        if not nums:
            trend.put(0, 0, '%s: no values yet' % p['name'], 244)
            return
        lo, hi = min(nums), max(nums)
        if hi == lo:
            hi = lo + 1
        rows = trend.height - 1
        trend.put(0, 0, '%s  %s  min %s  max %s' % (p['name'], point_name(p), fmt(p, min(nums)), fmt(p, max(nums))), 250)
        x0 = trend.width - len(h)
        for k, v in enumerate(h):
            if v is None:
                trend.put(x0 + k, rows, 'x', 196)
                continue
            y = rows - int((v - lo) * (rows - 1) / (hi - lo))
            trend.put(x0 + k, y, '*', 51)


def poll():
    with tdui.batch():
        status.text = 'Reading ...' + (' logging to ' + log_file[0] if log_file[0] else '')
    errors = 0
    for i, p in enumerate(points):
        try:
            raw = tinydesk.modbus_read(p['target'], p['unit'], p['table'], p['addr'], 1)[0]
            if p.get('signed') and raw >= 0x8000:
                raw -= 0x10000
            values[i] = scaled(p, raw) if p['table'] in ('hr', 'ir') else raw
            p['_err'] = ''
        except OSError as e:
            values[i] = None
            p['_err'] = str(e)
            errors += 1
        history[i].append(values[i])
        if len(history[i]) > TREND:
            history[i].pop(0)
    t = time.localtime()
    stamp = '%04d-%02d-%02d %02d:%02d:%02d' % t[:6]
    if log_file[0]:
        try:
            with open(log_file[0], 'a') as f:
                f.write(stamp + ',' + ','.join('' if v is None else fmt(p, v) for p, v in zip(points, values)) + '\n')
        except OSError as e:
            log_file[0] = None
            tdui.msgbox('Modbus Monitor', 'Logging stopped: %s' % e)
    show_list()
    show_bars()
    show_trend()
    status.text = '%s  %d point%s, %d error%s, every %d s%s' % (
        stamp[11:], len(points), '' if len(points) == 1 else 's', errors, '' if errors == 1 else 's', every[0],
        ('  log: ' + log_file[0]) if log_file[0] else '')


def ask(title, prompt, text=''):
    v = tdui.inputbox(title, prompt, text)
    if v is None:
        raise KeyboardInterrupt
    return v.strip()


def add(_):
    if len(points) >= MAX_POINTS:
        tdui.msgbox('Add a point', 'Up to %d points.' % MAX_POINTS)
        return
    last = points[-1] if points else {}
    try:
        target = ask('Add a point', 'Device: host[:port] for Modbus TCP,\nrtu[N][:baud] for RTU',
                     last.get('target', '192.168.1.50'))
        unit = int(ask('Add a point', 'Unit (slave) id, 1-247:', str(last.get('unit', 1))))
        t = tdui.msgbox('Add a point', 'Which table?', 'Holding reg|Input reg|Coil|Discrete in')
        if t < 0:
            return
        addr = int(ask('Add a point', 'Address (from 0):', str(last.get('addr', -1) + 1)))
        name = ask('Add a point', 'Name:', 'P%d' % (len(points) + 1))[:14] or 'P%d' % (len(points) + 1)
        p = {'name': name, 'target': target, 'unit': unit, 'table': TABLES[t], 'addr': addr}
        if t < 2:
            p['scale'] = float(ask('Add a point', 'Scale (value = raw x scale), e.g. 0.1:', '1'))
            p['units'] = ask('Add a point', 'Units (optional), e.g. C:')[:8]
            p['min'] = float(ask('Add a point', 'Bar: lowest value:', '0'))
            p['max'] = float(ask('Add a point', 'Bar: highest value:', '100'))
            p['signed'] = tdui.confirm('Add a point', 'Signed 16-bit value (-32768..32767)?')
        else:
            p['min'], p['max'] = 0.0, 1.0
    except KeyboardInterrupt:
        return
    except ValueError:
        tdui.msgbox('Add a point', 'That is not a number.')
        return
    points.append(p)
    save()
    show_list()
    lst.selected = len(points) - 1
    poll()


def remove(_):
    i = lst.selected
    if points and 0 <= i < len(points) and tdui.confirm('Remove', 'Remove %s?' % points[i]['name']):
        points.pop(i)
        values.pop(i)
        values.append(None)
        history.pop(i)
        history.append([])
        save()
        poll()


def write(_):
    i = lst.selected
    if not points or not 0 <= i < len(points):
        return
    p = points[i]
    if p['table'] in ('ir', 'di'):
        tdui.msgbox('Write', '%s is read-only (%s).' % (p['name'], 'input register' if p['table'] == 'ir' else
                                                         'discrete input'))
        return
    try:
        if p['table'] == 'co':
            raw = tdui.msgbox('Write', 'Set %s to:' % p['name'], 'ON|OFF')
            if raw < 0:
                return
            raw = 1 - raw
        else:
            v = float(ask('Write', 'New value for %s (%s):' % (p['name'], p.get('units', '')),
                          fmt(p, values[i]) if values[i] is not None else ''))
            raw = int(round((v - p.get('offset', 0.0)) / p.get('scale', 1.0)))
            if not (-32768 if p.get('signed') else 0) <= raw <= (32767 if p.get('signed') else 65535):
                tdui.msgbox('Write', 'Out of range for a 16-bit register.')
                return
            raw &= 0xFFFF
        tinydesk.modbus_write(p['target'], p['unit'], p['table'], p['addr'], raw)
    except KeyboardInterrupt:
        return
    except ValueError:
        tdui.msgbox('Write', 'That is not a number.')
        return
    except OSError as e:
        tdui.msgbox('Write', 'Write failed: %s' % e)
        return
    poll()


def log(b):
    if log_file[0]:
        log_file[0] = None
        b.text = 'Log'
        poll()
        return
    folder = '~'
    try:
        os.stat('/sd/TinyDesk')
        folder = '/sd/TinyDesk'
    except OSError:
        pass
    t = time.localtime()
    name = '%s/modbus_%04d%02d%02d_%02d%02d.csv' % ((folder,) + t[:5])
    try:
        with open(name, 'w') as f:
            f.write('time,' + ','.join('%s (%s)' % (p['name'], p.get('units', '')) for p in points) + '\n')
    except OSError as e:
        tdui.msgbox('Log', 'Cannot write %s: %s' % (name, e))
        return
    log_file[0] = name
    b.text = 'Stop log'
    poll()


timer = [None]


def set_every(_):
    v = tdui.inputbox('Interval', 'Read every how many seconds (1-3600)?', str(every[0]))
    try:
        every[0] = max(1, min(3600, int(v)))
    except (TypeError, ValueError):
        return
    save()
    start()


def start():
    if timer[0]:
        timer[0].cancel()
    timer[0] = w.every(every[0] * 1000, poll)


def selected(_):
    show_trend()


def resized(win, width, height):
    trend.resize(max(10, width - 2), max(3, height - 15))
    show_trend()


lst.on_select = selected
lst.on_activate = write
w.on_resize = resized
w.button(1, -1, 'Add', add)
w.button(9, -1, 'Remove', remove)
w.button(20, -1, 'Write', write)
w.button(30, -1, 'Log', log)
w.button(43, -1, 'Interval', set_every)
show_list()
if points:
    lst.selected = 0
    poll()
else:
    status.text = 'Add a point to start: a Modbus TCP or RTU device and a register.'
start()
tdui.run()
