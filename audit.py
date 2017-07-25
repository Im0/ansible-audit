# (C) 2017, John Imison <john@imison.net>

# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

'''
This module assists in auditing devices/systems with an ansible playbook.
Typically ansible stops on erroring tasks, however, this plugin relies on
tasks having 'ignore_errors: yes' so ansible continues processing the play
book.  This plugin then produces a report on success and failures in a number
of formats.

This plugin works around the fact that ansible will typically stop on failure,
or, ignore failures without maintaining accurate statistics.  This plugin
expects playbook tasks to fail and be ignored in the playbook which allows us
to keep statistics regarding the failures, warnings, ok's etc.

Example:
    To use this plugin in conjunction with your playbook, below are some
    options on how to run.

    This will audit the systems referenced in your site.yml playbook:

        $ AUDIT_NAME='My Systems' CUSTOMER="CUSTOMER" \
                ANSIBLE_CALLBACK_WHITELIST=audit \
                ansible-playbook --ask-sudo-pass site.yml -k


    Same, but, using a non-default location for the audit plugin and templates:

        $ AUDIT_NAME='My Systems' CUSTOMER="CUSTOMER" \
            ANSIBLE_CALLBACK_WHITELIST=audit ANSIBLE_CONFIG='./audit/ansible.cfg' \
            ansible-playbook --ask-sudo-pass ansible-audit-playbook-example/site.yml -k

    Where the ./audit/ansible.cfg contains a directive pointing to your callback
    plugins directory.  You may simply copy the default /etc/ansible/ansible.cfg and
    modified teh callback_plugins directive to suit my needs.  


'''

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import time
import json
import zipfile
import sys
import logging
from collections import defaultdict
import jinja2

from ansible.plugins.callback import CallbackBase


class CallbackModule(CallbackBase):
    """
    audit plugin to output audit results into JSON and HTML format for future
    processing.

    """
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'audit'
    CALLBACK_NEEDS_WHITELIST = True
    ''' Valid options for debugging:  'DEBUG'|'INFO'|False '''
    DEBUG = False

    TIME_FORMAT = "%b %d %Y %H:%M:%S"

    def __init__(self):
        """
        The below arguments are external arguments we receive from the shell
        using os.getenv.

        Args:
            AUDIT_NAME (str): This is the name of the audit we are carrying out
            CUSTOMER (str): Customer name, if, auditing a customer environment
        """
        super(CallbackModule, self).__init__()

        self.config = {
            "logFormat": '%(asctime)-15s: %(funcName)s: %(message)s',
            "working_dir": '/var/log/ansible/audits/',
            "filename_prepend": 'audit'
        }

        if not os.path.exists(self.config['working_dir']):
            os.makedirs(self.config['working_dir'])

        self.meta = {
            "audit_start_time": time.strftime(self.TIME_FORMAT, time.localtime()),
            "audit_end_time": 0,
            "customer": os.getenv('CUSTOMER', 'No customer specified'),
            "audit_name": os.getenv('AUDIT_NAME', 'No audit name specified'),
            "json_file": '',
            "html_report": '',
            "html_fruitsalad": '',
            "zipfile": '',
            "tasks": [],
        }

        self.stats = {
            "num_hosts": 0,
            "num_tasks": 0,
            "hosts_failed": 0,
            "tasks_failed": 0,
            "tasks_warning": 0,
            "tasks_skipped": 0,
            "tasks_ok": 0,
            "tasks_per_host": 0,
        }

        self.host_stats = defaultdict(dict)

        self.results = {}
        self.task = None
        self.play = None

        if self.DEBUG == 'DEBUG':
            logging.basicConfig(format=self.config['logFormat'], level=logging.DEBUG)
            logging.debug('debug logging enabled')
        elif self.DEBUG == 'INFO':
            logging.basicConfig(format=self.config['logFormat'], level=logging.INFO)
            logging.info('info logging enabled')
        else:
            logging.basicConfig(format=self.config['logFormat'], level=logging.CRITICAL)



    def _new_result(self, host, status, data):
        """Handle new results from incoming playbook tasks

        Check to see if there was an error in the results that has been returned
        and if so, we need to increment warning, and, decrement OK counts if the
        task was originally marked as OK.

        Also, check for the playbook stdout starting with WARNING as this suggests
        the playbook author wants a result to be marked as warning, but, ansible
        may have returned OK.

        Args:
            host (str): The hostname of the system the result is for
            status (str): The status of the task for this host
            data (dict): TODO: Are we using this?  Tidy up?

        Returns:
            dict: Returns a dict containing, task_name, play_name, stdout,
                stderr and the status.
        """
	stderr = ''
        stdout = ''

        logging.debug('%s (%s) - %s', host, status, data)
	if isinstance(data, dict):
            # If there is information in stderr we can assume the command
            # did not execute correctly and should WARN and remove OK count.
	    if 'stderr' in data.keys():
            	stderr = data['stderr']
                # If there is output in standard error output, the status is
                # NOT OK.  We need to WARN instead.
                if len(data['stderr']) >= 2 and status == 'OK':
                    status = 'WARNING'
                    self.stats['tasks_warning'] += 1
                    self.stats['tasks_ok'] -= 1
            else:
                stderr = ''

            if 'stdout' in data.keys():
                stdout = data['stdout']
                if stdout.startswith('WARNING') and status == 'FAILED':
                    status = 'WARNING'
                    self.stats['tasks_warning'] += 1
                    self.stats['tasks_failed'] -= 1
                elif stdout.startswith('WARNING') and status == 'OK':
                    status = 'WARNING'
                    self.stats['tasks_warning'] += 1
                    self.stats['tasks_ok'] -= 1

            else:
                stderr = ''

        return {
            'task_name': str(self.task),
            'play_name': str(self.play),
            'result_stdout': stdout,
            'result_stderr': stderr,
            'result_status': status
        }


    def _write_html(self):
        """Write out our vanilla HTML report
        """

        out_file = 'report-%s.html' % (os.getpid())
        self.meta['html_report'] = os.path.join(self.config['working_dir'], out_file)
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'audit_results.jinja')

	with open(self.meta['json_file']) as data_file:
            data = json.load(data_file)

        result = self.render(template_path, data)

        logging.info('Writing HTML to: %s', self.meta['html_report'])
        fh = open(self.meta['html_report'], 'w')
        fh.write(result)
        fh.close()

    def _write_fruit_salad(self):
        """Write out our fruit salad HTML report
        """

        out_file = 'fruit-salad-%s.html' % (os.getpid())
        self.meta['html_fruitsalad'] = os.path.join(self.config['working_dir'], out_file)
        template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'audit_fruitsalad.jinja')

        with open(self.meta['json_file']) as data_file:
            data = json.load(data_file)

        result = self.render(template_path, data)

        logging.info('Writing HTML fruitsalad to: %s', self.meta['html_fruitsalad'])
        fh = open(self.meta['html_fruitsalad'], 'w')
        fh.write(result)
        fh.close()

    def zip(self):
        """Zip up JSON, html report and fruitsalad files.
        """
        outFile = '%s-%s.zip' % (self.config['filename_prepend'], os.getpid())
        self.meta['zipfile'] = os.path.join(self.config['working_dir'], outFile)

        zf = zipfile.ZipFile("%s" % (self.meta['zipfile']), "w", zipfile.ZIP_DEFLATED)
        zf.write(self.meta['json_file'], os.path.basename(self.meta['json_file']))
        zf.write(self.meta['html_report'], os.path.basename(self.meta['html_report']))
        zf.write(self.meta['html_fruitsalad'], os.path.basename(self.meta['html_fruitsalad']))
        zf.close()
        logging.info('Zip file location: %s', self.meta['zipfile'])

    def tidyup(self):
        """Tidy up JSON, html report and fruit salad files
        """
        logging.info('Deleting JSON and HTML files')
        os.remove(self.meta['json_file'])
        os.remove(self.meta['html_report'])
        os.remove(self.meta['html_fruitsalad'])


    def render(self, tpl_path, context):
        """Render the jinja templates
        """
        path, filename = os.path.split(tpl_path)
        logging.info('Rendering template %s', filename)
        return jinja2.Environment(
            loader=jinja2.FileSystemLoader(path or './')).get_template(filename).render(context)



    def _save_results(self):
        """Saving the data to the JSON file
        """
        outFile = 'audit-%s.json' % (os.getpid())
        self.meta['json_file'] = os.path.join(self.config['working_dir'], outFile)

        results = self.results.copy()
        stats = self.stats.copy()
        meta = self.meta.copy()
        host_stats = self.host_stats.copy()
        d = dict()
        d = {
            'results': results,
            'stats': stats,
            'meta': meta,
            'host_stats': host_stats
            }

        logging.info('Saving JSON file to: %s', self.meta['json_file'])
        msg = json.dumps(d, sort_keys=True, indent=4)
        with open(self.meta['json_file'], "w") as fd:
            fd.write(msg)


    def _calculate_host_stats(self):
        """Calculate the individual host statistics

        We use these statistics in the HTML output for each host.  These results
        determine the class of the cells in the HTML.

        ie. If there are FAILED tasks, our HTML class will be "danger" (red)
        """
        host_list = sorted(self.results.keys())
        # for each host we've gathered details about
        for host in host_list:
            # Populate host status dict with defaults
            for status in ['SKIPPED', 'UNREACHABLE', 'OK', 'FAILED', 'WARNING']:
                self.host_stats[host][status] = 0

            # Loop over the host results and increment status counter
            for result in self.results[host]:
                if result['result_status'] == 'OK':
                    self.host_stats[host]['OK'] += 1
                elif result['result_status'] == 'FAILED':
                    self.host_stats[host]['FAILED'] += 1
                elif result['result_status'] == 'UNREACHABLE':
                    self.host_stats[host]['UNREACHABLE'] += 1
                elif result['result_status'] == 'SKIPPED':
                    self.host_stats[host]['SKIPPED'] += 1
                elif result['result_status'] == 'WARNING':
                    self.host_stats[host]['WARNING'] += 1




    def runner_on_failed(self, host, data, ignore_errors=False):
        """Routine for handling runner (task) failures

        Ansible calls this if a task in a playbook fails for a host. We use
        this to increment our statistics dictionary.
        """
        test = self.results.setdefault(str(host), [])
        test.append(self._new_result(str(host), 'FAILED', data))
        self.stats['tasks_failed'] += 1
        self.stats['num_tasks'] += 1


    def runner_on_ok(self, host, data):
        """Routine for handling runner (task) successes

        Ansible calls this if a task in a playbook succeeds for a host. We use
        this to increment our statistics dictionary.
        """
        test = self.results.setdefault(str(host), [])
        test.append(self._new_result(str(host), 'OK', data))
        self.stats['tasks_ok'] += 1
        self.stats['num_tasks'] += 1


    def runner_on_skipped(self, host, item=None):
        # ERROR/SKIPPED here needs capturing and handling properly.  skipped desn't resturn res
        # to pass onto _new_result.
        test = self.results.setdefault(str(host), [])
        test.append(self._new_result(str(host), 'SKIPPED', {}))
        self.stats['tasks_skipped'] += 1
        self.stats['num_tasks'] += 1


    def runner_on_unreachable(self, host, data):
        test = self.results.setdefault(str(host), [])
        test.append(self._new_result(str(host), 'UNREACHABLE', data))
        self.stats['hosts_failed'] += 1


    def playbook_on_stats(self, stats):
        self.meta['audit_end_time'] = time.strftime(self.TIME_FORMAT, time.localtime())
        self.stats['num_hosts'] = len(self.results.keys())
        self.stats['tasks_per_host'] = self.stats['num_tasks'] // self.stats['num_hosts']

        self._calculate_host_stats()

        self._save_results()
        self._calculate_host_stats()
        self._write_html()
        self._write_fruit_salad()
        self.zip()
        self.tidyup()
        logging.info('Stats dump: %s', json.dumps(self.stats))
        logging.info('Host stats dump: %s', json.dumps(self.host_stats))

    def v2_playbook_on_play_start(self, play):
        self.play = play

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.meta['tasks'].append(str(task.name))
        self.task = task.name
