#!/usr/bin/env python3
'''Move all disks for a given VM.'''
# pylint: disable=invalid-name
# pylint: disable=redefined-outer-name

import json
import logging
import re
import sys
import argparse

import requests


api_filename = 'api_credentials.json'
storage_target = 'vm-block-storage-VMs'

parser = argparse.ArgumentParser(
    description='''Print manifest of nodes/vms/storage devices.''')

parser.add_argument('-v', '--verbose', action='count', help="Be verbose, (multiples okay)")
parser.add_argument('-m', '--move', action='store_true', help="Print `qm move_disk' commands.")
parser.add_argument('-t', '--target', action='store', help="Print `qm move_disk' commands.")
parser.add_argument('-f', '--credfile', action='store', help="Use alternate credentials files (default={})".format(api_filename))

try:
    parsed_options, remaining_args = parser.parse_known_args()

except SystemExit as exc:
    print('''
Error parsing arguments.
''')
    sys.exit(1)

verbose_value = 0 if parsed_options.verbose is None else parsed_options.verbose
LOG_LEVEL = max(1, 30 - verbose_value * 10)
logging.basicConfig(format='%(asctime)-15s [%(levelname)s] %(message)s', level=LOG_LEVEL)

if parsed_options.target is not None:
    storage_target = parsed_options.target

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


def get_vm_config(client, BASE, node, vmid):
    '''Return configuration of select VM from selected node.'''

    config = json.loads(client.get(BASE+'/nodes/{}/qemu/{}/config'.format(node, vmid)).text)['data']

    logging.debug(config)
    return config



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

    for config, value in get_vm_config(client, URLBASE, node, vmid).items():
        m = re.match(r'(scsi|virtio|ide|sata|unused)\d+', config)
        if m:
            logging.info("%d/%s drive: %s:%s", vmid, name, config, value)

            #if value.startswith('none'):
            #    logging.info(" not attached?")
            #    continue
#
#            if 'cdrom' in value:
#                logging.info(" skipping cdrom")
#                continue

            if name in disk_map:
                disk_map[name].append((node, name, vmid, config, value))
            else:
                disk_map[name] = [(node, name, vmid, config, value)]

for vm, values in sorted(disk_map.items()):
    for value in sorted(values):
        if parsed_options.move:
            logging.debug(value)
            if 'cdrom' in value[4]:
                logging.debug("Skipping: cannot move CDROM images")
                continue

            if storage_target in value[4]:
                logging.info("Skipping: target (%s) is same as current location (%s)", storage_target, value[4])
                continue

            print("qm move_disk {} {} {}  --delete 1  \t# {}:{}".format(value[2], value[3], storage_target, value[0],value[1]))

        else:
            print("{} {:20s} {:3} {:9s} {}".format(*value))



sys.exit(0)
# End of line -- MCP
