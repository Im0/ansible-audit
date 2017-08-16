# audit

An Ansible callback plugin to assist in auditing environments in conjunction
with a playbook expecting errors to be present.


- [License](#license)
- [Description](#description)
- [Use Cases](#use_case)
- [How To Use](#usage)
- [Playbook](#playbook_example)
- [Output](#output)

## License

(C) 2017, John Imison <john@imison.net>

This file is part of Ansible

Ansible is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Ansible is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Ansible.  If not, see <http://www.gnu.org/licenses/>.


## Description

This module assists in auditing devices/systems with an ansible playbook.
Typically ansible stops on erroring tasks, however, this plugin relies on
tasks having 'ignore_errors: yes' so ansible continues processing the play
book.  This plugin then produces a report on success and failures in a number
of formats.

This plugin works around the fact that ansible will typically stop on failure,
or, ignore failures without maintaining desired statistics.  This plugin
expects playbook tasks to fail and be ignored in the playbook which allows us
to keep statistics regarding the failures, warnings, ok's etc.

## Use Cases

You might consider using this callback plugin if:

* You wish to audit desired state, but, not change state on a bunch of systems 

## Usage

First, either copy the following files to your ansible callback plugins
directory.  audit.py, audit_fruitsalad.jinja and audit_results.jinja.

### External variables

A number of variables can be passed through to the audit plugin modifying
configuration or providing content to the jinja templates.

* AUDIT_NAME - The name of the audit. If left blank, defaults to 'No audit name specified'
* CUSTOMER - A customer name.  If left blank, defaults to 'No customer specified'
* OUTPUT_DIR - Where to output the zip file containing the JSON and HTML files.
* DISPLAY_PATH - If 'TRUE', display path to zip file on finish.  Default is not to display.

Ansible specific:
* ANSIBLE_CALLBACK_WHITELIST - Instructs ansible to use the custom
  plugin.

### Examples

Example when files are in the ansible module directory:
    To use this plugin in conjunction with your playbook, below are some
    options on how to run::

```bash
        $ AUDIT_NAME='My Systems' CUSTOMER="CUSTOMER" \
            ANSIBLE_CALLBACK_WHITELIST=audit \
            DISPLAY_PATH=TRUE \
            ansible-playbook --ask-sudo-pass site.yml -k
```

This will audit the systems referenced in your site.yml playbook and output
a zip file into the self.config['working_dir'], and, print out the path to
the zip file.

Example, when the files are stored in a separate modules path:

```bash
        $ AUDIT_NAME='My Systems' CUSTOMER="CUSTOMER" \
            ANSIBLE_CALLBACK_WHITELIST=audit ANSIBLE_CONFIG='./audit/ansible.cfg' \
            OUTPUT_DIR=/tmp/audit/ DISPLAY_PATH=TRUE \
            ansible-playbook --ask-sudo-pass ansible-audit-playbook-example/site.yml -k
```

Where the ./audit/ansible.cfg contains a directive pointing to your callback
plugins directory.  I simply copied the default /etc/ansible/ansible.cfg and
modified the callback_plugins directive to suit my needs.  For instance:

```
callback_plugins   = /usr/share/ansible/plugins/callback:./:./audit
```

Tested with:
* ansible 2.3.0.0 & 2.3.1.0
* python version = 2.7.12 


## Playbook example

'ignore_errors: yes' is required as we don't want ansible stopping on failure.

'changed_when: false' is required as the commands/shell should NOT change any state.
We don't want ansible saying the result of the task is changed.

```
- name: 1. Failing task
  command: /bin/false
  ignore_errors: yes
  changed_when: false

- name: 2. Succeeding task
  command: /bin/false
  ignore_errors: yes
  changed_when: false

- name: 3. Warning task
  shell: |
    echo "WARNING: This task returned a warning."
    exit 1
  args:
    executable: /bin/bash
  ignore_errors: yes
  changed_when: false

- name: 4. Warning task
  shell: |
    echo "WARNING: This task returns a warning too."
    exit 0
  args:
    executable: /bin/bash
  ignore_errors: yes
  changed_when: false
```

For a complete example, check out: https://github.com/Im0/ansible-audit-playbook-example

## Output

The plugin will produce a zipfile within the configured directory defined in
self.config['working_dir'].  The zip file contains a JSON file and two HTML
files.  

'working_dir' can be overwritten by specifying the external variable OUTPUT_DIR.
ie.  OUTPUT_DIR=/tmp/ansible

Alter the jinja templates if you wish to adjust the look and feel of the HTML
output.

