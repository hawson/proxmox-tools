#!/usr/bin/env python3
'''Move all disks for a given VM.'''
# pylint: disable=invalid-name
# pylint: disable=redefined-outer-name
# pylint: disable=line-too-long


import json
import logging
import re
import sys
import argparse
from operator import itemgetter

import requests


api_filename = 'api_credentials.json'
storage_target = None

parser = argparse.ArgumentParser(
    description='''Print manifest of nodes/vms/storage devices.''')

parser.add_argument('-v', '--verbose', action='count', help="Be verbose, (multiples okay)")
parser.add_argument('-m', '--move', action='store_true', help="Print `qm move_disk' commands. (Also requires --target option)")
parser.add_argument('-t', '--target', action='store', help="Print `qm move_disk' commands.")
parser.add_argument('-f', '--credfile', action='store', help="Use alternate credentials files (default={})".format(api_filename))
parser.add_argument('-n', '--negate', action='count', help="Negate *ALL* filter rules, if present.")

parser.add_argument('Filter', nargs='*', action='store', help="Regex to filter results.  Applied to *entire* output line.")


try:
    parsed_options, remaining_args = parser.parse_known_args()

except SystemExit as exc:
    print('''
Error parsing arguments.
''')
    sys.exit(1)

verbose_value = 0 if parsed_options.verbose is None else parsed_options.verbose
LOG_LEVEL = max(1, 30 - verbose_value * 10)
logging.basicConfig(format='%(asctime)-11s %(levelname)-4.4s %(filename)s:%(funcName)s:%(lineno)-4d %(message)s', level=LOG_LEVEL)

if parsed_options.target is not None:
    storage_target = parsed_options.target


if parsed_options.move and parsed_options.target is None:
    print("""You must specifiy --target and --move together.""")
    sys.exit(1)

#######################################################

def load_cred(filename=api_filename):
    '''Load creds, so we don't embed them in code'''
    try:
        with open(filename) as jfile:
            data = json.load(jfile)
    except OSError as exc:
        logging.error("Failed opening %s: %s", filename, exc)


    return data

# ---------------------------------------------------
def make_api_connection(cred):
    '''Connect to the PVE API, and wrap the cookie goodness'''

    client = requests.session()

    URL = "https://{}:8006/api2/json/access/ticket".format(cred['host'])
    logging.debug("URL=%s", URL)
    data = {
        'username':cred['username'],
        'password':cred['password'],
    }
    auth_response = client.post(URL, data=data)

    logging.debug(auth_response)
    r = json.loads(auth_response.text)

    #csrf = r['data']['CSRFPreventionToken']
    ticket = r['data']['ticket']
    client.cookies.set('PVEAuthCookie', ticket)

    return client



def get_nodes(client, BASE):
    '''Get a list of PVE hardware nodes.'''

    nodes = []

    node_data = json.loads(client.get(BASE + '/nodes').text)['data']

    print(node_data)
    for node in node_data:
        name = node['node']
        nodes.append(name)

    return nodes


def get_vms(client, BASE):
    '''Get a list of VMs.'''

    vms = []

    vm_list_json = client.get(BASE+'/cluster/resources?type=vm')
    vm_list = json.loads(vm_list_json.text)
    vms.extend(vm_list['data'])

    logging.debug("vm_list=%s", vms)
    return vms


def get_vm_config(client, BASE, vm):
    '''Return configuration of select VM from selected node.'''

    config = json.loads(client.get(BASE+'/nodes/{}/{}/{}/config'.format(vm['node'], vm['type'], vm['vmid'], )).text)['data']

    logging.debug(config)
    return config


def display_moves(disk_map, Filter):
    '''Spit out list of move commands'''

    final_list = []

    for _, drives in disk_map.items():

        for drive in drives:
            # ('pve2', 'piercelab-dev', 120, 'virtio0', 'pve-storage1:120/vm-120-disk-0.qcow2,size=200G')

            logging.debug(drive)
            if 'cdrom' in drive[4]:
                logging.debug("Skipping: cannot move CDROM images")
                continue

            if storage_target in drive[4]:
                logging.info("Skipping: target (%s) is same as current location (%s)", storage_target, drive[4])
                continue

            cmd = "qm move_disk {} {:7} {}  --delete 1".format(drive[2], drive[3], storage_target)
            comment = "# {}:{}".format(drive[0], drive[1])

            cmd = cmd.ljust(55) + comment


            final_list.append((itemgetter(0, 2, 1, 3)(drive), cmd))

    # Finally, print the nicely sorted list
    for drive in sorted(final_list):
        match = re.search(Filter, drive[-1])
        logging.debug("Matched filter: %s", match)
        if match and not parsed_options.negate:
            print(drive[-1])
        elif not match and parsed_options.negate:
            print(drive[-1])


def display_devices(disk_map, Filter):
    '''pretty-print list mapping of node-vm-storage'''
    final_list = []
    for _, drives in disk_map.items():
        for drive in drives:
            logging.debug(drive)
            final_list.append(drive)

    for drive in sorted(final_list, key=itemgetter(0, 2, 1, 3, 4)):
        string = "{} {:20s} {:3} {:9s} {}".format(*drive)
        match = re.search(Filter, string)
        logging.debug("Matched: %s", match)
        if match and not parsed_options.negate:
            print(string)
        elif not match and parsed_options.negate:
            print(string)


def make_filter(Filter):
    return r'|'.join(Filter)


################################################################

# make new session ot the API
cred = load_cred('api_credentials.json')
client = make_api_connection(cred)


# GET NODES
URLBASE = 'https://{}:8006/api2/json'.format(cred['host'])



vms = get_vms(client, URLBASE)

disk_map = {}

for vm in vms:

    node = vm['node']
    name = vm['name']
    vmid = vm['vmid']

    for config, value in get_vm_config(client, URLBASE, vm).items():
        m = re.match(r'(scsi|virtio|ide|sata|unused)\d+', config)
        if m:
            logging.info("%d/%s drive: %s:%s", vmid, name, config, value)

            if name in disk_map:
                disk_map[name].append((node, name, vmid, config, value))
            else:
                disk_map[name] = [(node, name, vmid, config, value)]

if parsed_options.Filter:
    Filter = make_filter(parsed_options.Filter)
else:
    Filter = r'.+'

if parsed_options.move:
    # pretty-print a list of `qm move_disk' commands
    display_moves(disk_map, Filter)

else:
    display_devices(disk_map, Filter)

sys.exit(0)
# End of line -- MCP
