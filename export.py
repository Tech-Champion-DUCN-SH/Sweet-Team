
import sys;
import re;
import json;
import subprocess;
import MySQLdb as db;

import setting

def cols(dump):
  if dump < 1: return None
  if not re.match('-[-\s]*-', dump[-1]): return None

  cols = []
  name = dump[-2]
  dash = dump[-1]

  last = 0
  for i in range(0, len(dash)):
    if dash[i] == '-': continue
    cols.append({'name': name[last:i].strip(), 'index': [last, i]});
    last = i + 1;
  if last < len(dash):
    cols.append({'name': name[last:i].strip(), 'index': [last, len(dash)]});

  return { 'name': dump[-3].strip(), 'cols': cols }

def rows(dump, cols):
  rows = []
  for i in range(0, len(dump)):
    text = dump[i]
    line = {}
    for j in range(0, len(cols)):
      defs = cols[j]
      indx = defs['index']
      line[defs['name']] = text[indx[0]: indx[1]].strip()
    rows.append(line)
  return rows


# read ovsdb-client dump
def ovsdb(cmd):
  process = subprocess.Popen(cmd,
                             stdout=subprocess.PIPE, 
                             stderr=subprocess.PIPE)
  out = process.stdout

  head = None
  cach = {}

  line = out.readline()
  dump = [line]

  while line:
    if len(line.strip()) > 1:
      if head is None:
        head = cols(dump)
        if head is not None: dump = []
      else:
        cach[head['name']] = cach.get(head['name'], [])
        cach[head['name']].extend(rows(dump, head["cols"]))
        dump = []
    else:
      head = None
      dump = []
    line = out.readline()
    dump.append(line)
  return cach


def links(cmd):
  process = subprocess.Popen(cmd,
                             stdout=subprocess.PIPE, 
                             stderr=subprocess.PIPE)
  out = process.stdout
  cach = {}
  line = out.readline()
  while line: 
    match = re.match(r'^\d+:(.+):', line)
    if match is not None: 
      name = match.group(1).strip()
      cach[name] = ""
    match = re.match(r'^\s+(veth|tun|bridge)', line)
    if match is not None: 
      cach[name] = match.group(1).strip()
    line = out.readline()
  return cach
    
 


def main():
  cach = ovsdb(setting.cmd['ovsdb']) 
  link = links(setting.cmd['links'])

  vmid = {}
  data = { 'peers': {}, 'interfaces': {}, 'ports': {}, 'bridges': {}, 'instances': {} }
  for row in cach['Interface table']:
    item = {}    
    for i in [ '_uuid', 'name', 'type', 'external_ids' ]:
      item[i] = row[i].strip(' "[]{}')

    if len(item['name'].strip()) > 0: 
      ldev = link.get(item['name'].strip(), None)
      if ldev is not None:
        item['device_type'] = ldev.strip()

    for i in item['external_ids'].split(','):
      if i.strip().startswith('vm-uuid'):
        item['vm-uuid'] = i[9:].strip('"')
        continue
      if i.strip().startswith('iface-id'):
        item['iface-id'] = i[10:].strip('"')
        continue

    data['interfaces'][item['_uuid']] = item

    if item['name'].startswith('int-br'):
       data['peers'].setdefault(item['name'][7:], []).append(item['_uuid'])

    if item['name'].startswith('phy-br'):
       data['peers'].setdefault(item['name'][7:], []).append(item['_uuid'])

  for row in cach['Port table']:
    item = {}
    for i in [ '_uuid', 'interfaces', 'tag' ]:
      item[i] = row[i].strip(' "[]{}')
    item['interfaces'] = item['interfaces'].split(',')
    item['interfaces'] = [ x.strip() for x in item['interfaces'] ]
    data['ports'][item['_uuid']] = item

  for row in cach['Bridge table']:
    item = {}
    for i in [ '_uuid', 'name', 'ports' ]:
      item[i] = row[i].strip(' "[]{}')
    item['ports'] = item['ports'].split(',')
    item['ports'] = [ x.strip() for x in item['ports'] ]
    data['bridges'][item['_uuid']] = item


  con = db.connect(**setting.sql)
  cur = con.cursor()
  cur.execute('select * from ports;')
  des = [i[0] for i in cur.description]
  
  for row in cur.fetchall():
    item = {}
    for i in range(0, len(row)): item[des[i]] = row[i]
    inst = { 'device_id': item['device_id'], 'name': item['name'], 'interfaces': [] }
    data['instances'].setdefault(item['device_id'], inst)['interfaces'].append(item['id'])

  print json.dumps(data);

if __name__ == "__main__":
  sys.exit(main())
