#!/usr/bin/python

DOCUMENTATION = '''
---
module: top_compute
short_description: Create Compute Group via Trowel API
version: '1.0'
prerequisites:
    - create token:
      curl -k -u d659535 https://trowel/api/user/token
      then save it under '~/.top_token'

options:
  state:
    type: str
    required: false
    default: present
    choices:
      - present
      - absent
      - update
  sleep:
    type: int
    required: false
    default: '3'
    description: time to wait for nodes to be created (minutes)
  token:
    required: false
    default: '~/.top_token'
  compute_count:
    type: int
    required: false
  compute_limit:
    type: int
    required: false
  subdomain:
    type: str
    required: true
  environment:
    type: str
    required: true
  size:
    type: str
    required: false
    default: small
    choices:
      - micro
      - small
      - medium
      - large
      - xlarge
  template:
    type: str
    required: true
  ssl:
    type: str
    required: false
    default: null
  disable_at:
    type: str
    required: false
    default: null
    example: 2015-09-25T02:34:18+00:00
  billing_code:
    type: str
    required: false
    default: null
    example: WBS123
  project_uuid:
    type: str
    required: true
  edn:
    type: bool
    required: false
    default: false
  routing:
    type: str
    required: false
    default: vip
  ports:
    type: list
    required: false
    default: ['80/http', '443/https']
  compute_uuid:
    description:
      - ComputeGroup uuid
      - Only used to delete the compute group
    type: str
    required: false
    default: ''
'''

EXAMPLES = '''
---
- name: Test Top Compute
  hosts: localhost
  vars:
    site: 'mco-production'
    token: '~/.top_token'

  tasks:
    - name: Create Compute Group
      top_compute:
        site: "{{ site }}"
        token: "{{ token }}"
        size: 'small'
        template: 'top-centos6-x86_64-0.149'
        project_uuid: 'aa1d9b99-4bb9-47a1-8873-53fe369d5462'
        subdomain: 'lenfree'
        environment: 'test'

    - name: Delete Compute Group
      top_compute:
        site: "{{ site }}"
        token: "{{ token }}"
        state: absent
        compute_uuid: facfb25a-2228-4981-a304-4791718a2d79

    - name: Update Compute Group
      top_compute:
          site: "{{ site }}"
          token: "{{ token }}"
          state: update
          compute_uuid: facfb25a-2228-4981-a304-4791718a2d79
          subdomain: 'lenfree'
          environment: 'test'
          compute_count: '1'

      # size, template, subdomain, environment, compute_uuid cannot be updated.
'''

from ansible.module_utils.basic import *
import httplib
import json
import os
import time

sites = {
    'localhost': 'localhost:8080',
}


class TopException(Exception):
    pass


class TopCompute(object):
    def __init__(self, site, params, sleep, token_path):
        try:
            with file(os.path.expanduser(token_path), 'r') as token:
                self.token = token.read().strip()
        except IOError:
            raise TopException('Failed to import: %s' % token_path)

        self.trowel_host = sites[site]
        self.sleep = int(sleep) * 6
        self.params = params
        self.header = {
            'Content-type': 'application/json',
            'Authorization': 'Token token=%s app=ansible' % self.token
        }

    def create_compute_group(self):
        for key in ['subdomain', 'environment', 'project_uuid', 'template']:
            if not self.params[key]:
                raise TopException('Attribute %s is missing.' % key)

        params = json.dumps({
            'size': self.params['size'],
            'compute_count': self.params['compute_count'],
            'compute_limit': self.params['compute_limit'],
            'subdomain': self.params['subdomain'],
            'environment': self.params['environment'],
            'template': self.params['template'],
            'ssl': self.params['ssl'],
            'disable_at': self.params['disable_at'],
            'billing_code': self.params['billing_code'],
            'project_uuid': self.params['project_uuid'],
            'edn': self.params['edn'],
            'routing': self.params['routing'],
            'ports': self.params['ports']
        })

        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='PATCH',
            headers=self.header,
            url='/api/compute_groups',
            body=params
        )
        response = conn.getresponse()
        conn.close()
        result = '%s %s' % (response.status, response.reason)

        if not response.status == 201:
            raise TopException('PATCH ERROR: %s' % result)
        self.wait_for_chisel()

    def update_compute_group(self):
        params = json.dumps({
            'compute_count': self.params['compute_count'],
            'compute_limit': self.params['compute_limit'],
            'ssl': self.params['ssl'],
            'disable_at': self.params['disable_at'],
            'billing_code': self.params['billing_code'],
            'edn': self.params['edn'],
            'routing': self.params['routing'],
            'ports': self.params['ports']
        })

        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='PATCH',
            headers=self.header,
            url='/api/compute_groups/%s' % self.get_compute_group_url(),
            body=params
        )
        response = conn.getresponse()
        conn.close()
        result = '%s %s' % (response.status, response.reason)

        if not response.status == 200:
            raise TopException('UPDATE ERROR: %s' % result)

    def delete_compute_group(self):
        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='DELETE',
            headers=self.header,
            url='/api/compute_groups/%s' % self.get_compute_group_url()
        )
        response = conn.getresponse()
        conn.close()
        result = '%s %s' % (response.status, response.reason)

        if not response.status == 200:
            raise TopException('DELETE ERROR: %s' % result)

    def compute_group_exists(self):
        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='GET',
            headers=self.header,
            url='/api/compute_groups/%s' % self.get_compute_group_url()
        )
        response = conn.getresponse()
        conn.close()
        result = '%s %s' % (response.status, response.reason)

        if response.status == 200:
            return True
        elif response.status == 404:
            return False
        else:
            raise TopException('GET ERROR: %s' % result)

    def get_compute_group_url(self):
        if self.params['compute_uuid']:
            return self.params['compute_uuid']
        else:
            if not self.params['subdomain'] or not self.params['environment']:
                raise TopException('subdomain or environment is missing.')
            return '%s-%s' % (
                self.params['subdomain'],
                self.params['environment']
            )

    def check_node_state(self):
        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='GET',
            headers=self.header,
            url='/api/compute_groups/%s' % self.get_compute_group_url()
        )
        response = conn.getresponse()
        result = '%s %s' % (response.status, response.reason)

        if response.status == 200:
            return json.load(response)['nodes']['allocate']
        else:
            TopException('check_node_state error: %s' % result)

    def wait_for_chisel(self):
        for _ in range(self.sleep):
            if not self.check_node_state():
                return
            else:
                time.sleep(10)

        raise TopException('Timed out. Something is wrong with chisel or vSphere.')


def main():
    fields = {
        'site': {
            'type': 'str',
            'required': True,
            'choices': [
                'cly-production',
                'cly-non-production',
                'stl-production',
                'stl-non-production',
                'mco-production',
                'localhost'
            ]},
        'token': {'type': 'str', 'default': '~/.top_token'},
        'sleep': {'type': 'int', 'default': '3'},
        'compute_count': {'type': 'int'},
        'compute_limit': {'type': 'int'},
        'subdomain': {'type': 'str'},
        'environment': {'type': 'str'},
        'template': {'type': 'str', 'default': 'latest'},
        'ssl': {'type': 'str'},
        'disable_at': {'type': 'str'},
        'billing_code': {'type': 'str'},
        'project_uuid': {'type': 'str'},
        'edn': {'type': 'bool', 'default': False},
        'routing': {'type': 'str', 'default': 'vip'},
        'compute_uuid': {'type': 'str'},
        'ports': {'type': 'list', 'default': ['80/http', '443/https']},
        'size': {
            'type': 'str',
            'default': 'small',
            'choices': ['micro', 'small', 'medium', 'large', 'xlarge']
        },
        'state': {
            'default': 'present',
            'type': 'str',
            'choices': ['present', 'absent', 'update']
        },
    }

    module = AnsibleModule(argument_spec=fields, supports_check_mode=True)
    compute = TopCompute(
        site=module.params['site'],
        sleep=module.params['sleep'],
        token_path=module.params['token'],
        params=module.params
    )

    try:
        exist = compute.compute_group_exists()
    except TopException as err:
        module.fail_json(msg=str(err))

    if module.params['state'] == 'absent':
        if exist:
            if not module.check_mode:
                try:
                    compute.delete_compute_group()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)
    elif module.params['state'] == 'update':
        if exist:
            if not module.check_mode:
                try:
                    compute.update_compute_group()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)
        else:
            if not module.check_mode:
                try:
                    compute.create_compute_group()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)
    else:   # state == 'present'
        if not exist:
            if not module.check_mode:
                try:
                    compute.create_compute_group()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)

    module.exit_json(changed=False)

if __name__ == '__main__':
    main()
