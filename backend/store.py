import json, os, re, sqlite3, sys, threading
from pathlib import Path
from fastapi import HTTPException

def _data_root():
    if os.environ.get('D2S_DATA_DIR'):
        return Path(os.environ['D2S_DATA_DIR']).resolve()
    if getattr(sys, '_MEIPASS', None):
        # Frozen: keep data writable next to the executable, not in the temp unpack dir.
        return Path(sys.executable).parent / 'data'
    return Path('data').resolve()

ROOT = _data_root()
ROOT.mkdir(parents=True, exist_ok=True)
LOCK = threading.RLock()

def connection():
    c = sqlite3.connect(ROOT / 'projects.sqlite3')
    c.execute('CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    return c

def save(p):
    with connection() as c:
        c.execute('INSERT OR REPLACE INTO projects VALUES (?,?)', (p['id'], json.dumps(p, ensure_ascii=False)))

def get(pid):
    with connection() as c:
        row = c.execute('SELECT body FROM projects WHERE id=?', (pid,)).fetchone()
    if not row:
        raise HTTPException(404, '项目不存在')
    return json.loads(row[0])

def all_projects():
    with connection() as c:
        return [json.loads(r[0]) for r in c.execute('SELECT body FROM projects ORDER BY rowid DESC')]

def pdf_path(pid):
    get(pid)
    return ROOT / (pid + '.pdf')

def check_revision(p, revision):
    if p['revision'] != revision:
        raise HTTPException(409, '项目已更新，请刷新后重试；本次编辑未写入')

def effective(record):
    return {**record['raw'], **record['edits']}

def _pin_sort_key(item):
    key, record = item
    number = str(effective(record).get('number', key))
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r'(\d+)', number) if part)

def _is_power_name(name):
    """Treat ground/power-supply names as power even when the model mislabels the
    electrical type (e.g. PGND returned as Passive). Repeated power names stay
    un-suffixed."""
    return bool(re.search(r'(GND|VSS)', name) or re.match(r'^(VCC|VDD|AVCC|VCCO|VBATT|VREF|VIN)', name))


def normalize_symbol_names(p):
    """Derive stable, unique default symbol names without touching human edits.

    Repeated Power pin names are intentionally retained. For every other repeated
    datasheet name, non-Power pins receive a physical-pin-order suffix (NAME1,
    NAME2, ...). original_name always remains the unmodified datasheet value.
    """
    groups = {}
    for key, record in p['pins'].items():
        if 'symbol_name' not in record['edits']:
            record['raw']['symbol_name'] = record['raw']['original_name']
        original = record['raw']['original_name'].strip()
        if original:
            groups.setdefault(original.casefold(), []).append((key, record))
    for items in groups.values():
        if len(items) < 2:
            continue
        non_power = [item for item in sorted(items, key=_pin_sort_key)
                     if effective(item[1])['electrical_type'] != 'Power'
                     and not _is_power_name(effective(item[1])['original_name'])]
        for index, (_, record) in enumerate(non_power, start=1):
            if 'symbol_name' not in record['edits']:
                record['raw']['symbol_name'] = f"{record['raw']['original_name']}{index}"

def _side_of(pin):
    """Classify a pin into a placement side: 'right', 'bidir', 'nc', or 'left'."""
    if pin.get('kind') in ('NC', 'DNC', 'exposed_pad', 'shield'):
        return 'nc'
    et = pin.get('electrical_type', 'Unknown')
    if et in ('Output', 'Open Collector', 'Open Emitter', '3-State'):
        return 'right'
    if et == 'Bidirectional':
        return 'bidir'
    return 'left'


def normalize_positions(p):
    """Place pins by function group: outputs right, NC pins grouped at the bottom,
    bidirectional pins balance the two sides for a roughly symmetric symbol, and
    everything else (inputs, clock, control, power, ground) goes left. Top is never
    used. Only pins without a manual position edit are affected."""
    editable = [key for key, r in p['pins'].items() if 'position' not in r['edits']]
    left, right, bidir, nc = [], [], [], []
    for key in editable:
        side = _side_of(effective(p['pins'][key]))
        if side == 'nc':
            nc.append(key)
        elif side == 'right':
            right.append(key)
        elif side == 'bidir':
            bidir.append(key)
        else:
            left.append(key)
    # Bidirectional pins are flexible: send them to whichever side has fewer pins.
    for key in bidir:
        (left if len(left) <= len(right) else right).append(key)
    for key in left:
        p['pins'][key]['raw']['position'] = 'Left'
    for key in right:
        p['pins'][key]['raw']['position'] = 'Right'
    for key in nc:
        p['pins'][key]['raw']['position'] = 'Bottom'


def normalize_electrical_types(p):
    """Normalize Unknown electrical_type to Passive for every pin (raw only, so
    explicit user edits remain authoritative)."""
    for record in p['pins'].values():
        if str(record['raw'].get('electrical_type', '')).strip().lower() == 'unknown':
            record['raw']['electrical_type'] = 'Passive'


def merge(p, pins):
    # A pre-parse undo snapshot must never restore stale model results.
    p['undo'] = []
    for pin in pins:
        number = pin['number']
        record = p['pins'].get(number)
        if record is None:
            p['pins'][number] = {'raw': pin, 'edits': {}, 'review': 'unreviewed', 'conflicts': [], 'versions': [pin]}
            continue
        old = record['raw']
        record['versions'].append(pin)
        # symbol_name is a backend-derived default; explicit user edits live in
        # record['edits'] and remain authoritative across every reparse.
        for field in ['original_name','electrical_type','kind','group','part']:
            if old[field] != pin[field]:
                msg = f'{field}: {old[field]} → {pin[field]}'
                if msg not in record['conflicts']:
                    record['conflicts'].append(msg)
                record['review'] = 'conflict'
        # Conflicting older labels remain in versions, not in the current evidence set.
        previous_evidence = old['evidence'] if old['original_name']==pin['original_name'] else []
        pin['evidence'] = list({json.dumps(e, sort_keys=True): e for e in previous_evidence + pin['evidence']}.values())
        record['raw'] = pin
        # Explicit edits remain authoritative, including after reparsing.
    normalize_symbol_names(p)
    normalize_positions(p)
    p['revision'] += 1
