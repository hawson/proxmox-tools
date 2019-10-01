#!/usr/bin/env python3
'''Move all disks for a given VM.'''
# pylint: disable=invalid-name
# pylint: disable=redefined-outer-name

import json
import logging
import re
import sys
import requests

LOG_LEVEL = 21
logging.basicConfig(format='%(asctime)-15s [%(levelname)s] %(message)s', level=LOG_LEVEL)

#######################################################

def load_cred(filename='api_credentials.json'):
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

            if value.startswith('none'):
                logging.info(" not attached?")
                continue

            if name in disk_map:
                disk_map[name].append((config, value))
            else:
                disk_map[name] = [(config, value)]

for vm, disks in sorted(disk_map.items()):
    for disk in sorted(disks):
        print("{:20s}: {:10s}{}".format(vm, *disk))


sys.exit(0)
# End of line -- MCP
