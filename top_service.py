#!/usr/bin/python

DOCUMENTATION = '''
---
module: top_service
short_description: Create Service via Trowel API
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
  token:
    required: false
    default: '~/.top_token'
  subdomain:
    type: str
    required: true
  environment:
    type: str
    required: true
  ssl:
    type: str
    required: false
    default: null
  public:
    type: bool
    default: false
  virtual_ip:
    type: str
  description:
    type: str
  project_uuid:
    type: str
    required: true
  compute_group:
    type: str
'''

EXAMPLES = '''
---
- name: Test Top Service
  hosts: localhost
  vars:
    site: 'stl-non-production'
    project_uuid: '6113e007-293d-45d3-be6b-6b78798b8f3e'
    token: '.token-stl-np'

  tasks:
    - name: Service drifter-charlotte
      top_service:
        site: "{{ site }}"
        token: "{{ token }}"
        state: present
        project_uuid: "{{ project_uuid }}"
        subdomain: 'drifter'
        environment: 'charlotte'
        compute_group: 'drifter-lenfree'
'''

from ansible.module_utils.basic import *
import httplib
import json
import os

sites = {
    'localhost': 'localhost:8080',
}


class TopException(Exception):
    pass


class TopService(object):
    def __init__(self, site, token_path, params):
        try:
            with file(os.path.expanduser(token_path), 'r') as token:
                self.token = token.read().strip()
        except IOError:
            raise TopException('Failed to import: %s' % token_path)

        self.trowel_host = sites[site]
        self.params = params
        self.header = {
            'Content-type': 'application/json',
            'Authorization': 'Token token=%s app=ansible' % self.token
        }

    def get_service_url(self):
        if self.params['uuid']:
            return self.params['uuid']
        else:
            if not self.params['subdomain'] or not self.params['environment']:
                raise TopException('subdomain or environment is missing.')
            return '%s-%s' % (
                self.params['subdomain'],
                self.params['environment']
            )

    def service_exists(self):
        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='GET',
            headers=self.header,
            url='/api/services/%s' % self.get_service_url()
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

    def create_service(self):
        for key in ['subdomain', 'environment', 'project_uuid']:
            if not self.params[key]:
                raise TopException('Attribute %s is missing.' % key)

        params = json.dumps({
            'subdomain': self.params['subdomain'],
            'environment': self.params['environment'],
            'ssl': self.params['ssl'],
            'public': self.params['public'],
            'virtual_ip': self.params['virtual_ip'],
            'description': self.params['description'],
            'project_uuid': self.params['project_uuid'],
            'compute_group_uuid': self.params['compute_group']
        })

        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='POST',
            headers=self.header,
            url='/api/services',
            body=params
        )
        response = conn.getresponse()
        conn.close()
        result = '%s %s' % (response.status, response.reason)

        if not response.status == 201:
            raise TopException('POST ERROR: %s' % result)

    def delete_service(self):
        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='DELETE',
            headers=self.header,
            url='/api/services/%s' % self.get_service_url()
        )
        response = conn.getresponse()
        conn.close()
        result = '%s %s' % (response.status, response.reason)

        if not response.status == 200:
            raise TopException('DELETE ERROR: %s' % result)

    def update_service(self):
        params = json.dumps({
            'subdomain': self.params['subdomain'],
            'environment': self.params['environment'],
            'ssl': self.params['ssl'],
            'public': self.params['public'],
            'virtual_ip': self.params['virtual_ip'],
            'description': self.params['description'],
            'uuid': self.params['uuid'],
            'project_uuid': self.params['project_uuid'],
            'compute_group_uuid': self.params['compute_group']
        })

        conn = httplib.HTTPConnection(self.trowel_host)
        conn.request(
            method='PATCH',
            headers=self.header,
            url='/api/services/%s' % self.get_service_url(),
            body=params
        )
        response = conn.getresponse()
        conn.close()
        result = '%s %s' % (response.status, response.reason)

        if not response.status == 200:
            raise TopException('UPDATE ERROR: %s' % result)


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
        'subdomain': {'type': 'str'},
        'environment': {'type': 'str'},
        'ssl': {'type': 'str'},
        'public': {'type': 'bool', 'default': False},
        'virtual_ip': {'type': 'str'},
        'description': {'type': 'str'},
        'project_uuid': {'type': 'str'},
        'uuid': {'type': 'str'},
        'compute_group': {'type': 'str'},
        'state': {
            'default': 'present',
            'type': 'str',
            'choices': ['present', 'absent', 'update']
        },
    }

    module = AnsibleModule(argument_spec=fields, supports_check_mode=True)
    service = TopService(
        site=module.params['site'],
        token_path=module.params['token'],
        params=module.params
    )

    try:
        exist = service.service_exists()
    except TopException as err:
        module.fail_json(msg=str(err))

    if module.params['state'] == 'absent':
        if exist:
            if not module.check_mode:
                try:
                    service.delete_service()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)
    elif module.params['state'] == 'update':
        if exist:
            if not module.check_mode:
                try:
                    service.update_service()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)
        else:
            if not module.check_mode:
                try:
                    service.create_service()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)
    else:   # state == 'present'
        if not exist:
            if not module.check_mode:
                try:
                    service.create_service()
                except TopException as err:
                    module.fail_json(msg=str(err))
            module.exit_json(changed=True)

    module.exit_json(changed=False)

if __name__ == '__main__':
    main()
