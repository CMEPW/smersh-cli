import argparse
import sys
from datetime import datetime, timezone

import requests
from cmd2 import Cmd, Cmd2ArgumentParser, with_argparser, with_argument_list
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .api import SmershAPI, APIRoles
from .models import User, Mission, Client, Vuln, PositivePoint, NegativePoint, Model, Host, Step, HostVuln, Impact
from .utils import date

TABLE_BOX_TYPE = box.ROUNDED
COMMAND_PROMPT = '\x1b[1;31mSMERSH {}>>\x1b[0m '


def has_ipython():
    try:
        import IPython
        return True
    except:
        return False


def get_show_parser():
    parser = Cmd2ArgumentParser()

    parser.add_argument(
        'model',
        nargs='?',
        choices=['mission', 'user', 'client', 'vuln', 'positive_point', 'negative_point', 'step', 'host', 'impact'],
        default=None,
        help='The object type to query information about.'
    )

    parser.add_argument(
        'ids',
        nargs='*',
        type=int,
        help='A list of identifiers (separated by spaces) of specific objects to print information about. If this '
             'list is empty, the program will print every object.'
    )

    parser.add_argument(
        '-r',
        '--raw',
        action='store_true',
        help='Whether to print the data in raw (without formatting) or in a table. Default is to print in a table.'
    )

    return parser


def get_use_parser():
    parser = Cmd2ArgumentParser()

    parser.add_argument(
        'model',
        choices=['mission', 'user', 'client', 'vuln', 'positive_point', 'negative_point', 'step', 'host', 'host_vuln'],
        help='The object type to query information about.'
    )

    parser.add_argument(
        'id',
        nargs='?',
        type=int,
        default=None,
        help='An optional identifier. If omitted, the command will assume you want to create a new object.'
    )

    return parser


def get_assign_parser(model):
    def object_id_checker(o):
        i = int(o)

        if i < 0:
            raise argparse.ArgumentTypeError('The object ID must be positive')

        return o

    def bool_checker(v):
        if isinstance(v, bool):
            return v
        if v.lower() in ('yes', 'true', 't', 'y', '1'):
            return True
        elif v.lower() in ('no', 'false', 'f', 'n', '0'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')

    def role_checker(s):
        if hasattr(APIRoles, s):
            return APIRoles[s].name

        raise argparse.ArgumentTypeError(f'Invalid role name: {s}')

    def date_checker(s):
        if s.lower() == 'now':
            return date.date_to_iso(date.now())

        return date.date_to_iso(date.date_from_iso(s))

    def add_str_subparser(_subparsers, field_name):
        str_subparser = _subparsers.add_parser(field_name)
        str_subparser.add_argument('value', type=str)

    def add_list_subparser(_subparsers, field_name, item_type=None, choices=None):
        assert(not ((item_type is None) and (choices is None)))

        list_subparser = _subparsers.add_parser(field_name)
        list_subparser.add_argument('action', choices=['add', 'remove'])

        if choices is None:
            list_subparser.add_argument('value', nargs='+', type=item_type)
        else:
            list_subparser.add_argument('value', nargs='+', choices=choices)

    def add_bool_subparser(_subparsers, field_name):
        bool_subparser = _subparsers.add_parser(field_name)
        bool_subparser.add_argument('value', type=bool_checker)

    def add_object_subparser(_subparsers, field_name):
        object_subparser = _subparsers.add_parser(field_name)
        object_subparser.add_argument('value', type=object_id_checker)

    def add_date_subparser(_subparsers, field_name):
        date_subparser = _subparsers.add_parser(field_name)
        date_subparser.add_argument('value', type=date_checker)

    parser = Cmd2ArgumentParser()
    subparsers = parser.add_subparsers(dest='field')

    if isinstance(model, Mission):
        add_str_subparser(subparsers, 'name')
        add_date_subparser(subparsers, 'start_date')
        add_str_subparser(subparsers, 'path_to_codi')
        add_date_subparser(subparsers, 'end_date')
        add_list_subparser(subparsers, 'users', item_type=object_id_checker)
        add_bool_subparser(subparsers, 'nmap')
        add_bool_subparser(subparsers, 'nessus')
        add_bool_subparser(subparsers, 'nmap_filer')
        add_bool_subparser(subparsers, 'nessus_filer')
        add_object_subparser(subparsers, 'mission_type')
        add_str_subparser(subparsers, 'credentials')
        add_list_subparser(subparsers, 'clients', item_type=object_id_checker)
        add_list_subparser(subparsers, 'steps', item_type=object_id_checker)

    elif isinstance(model, User):
        add_str_subparser(subparsers, 'username')
        add_str_subparser(subparsers, 'password')
        add_list_subparser(subparsers, 'roles', item_type=role_checker)
        add_bool_subparser(subparsers, 'enabled')
        add_list_subparser(subparsers, 'missions', item_type=object_id_checker)
        add_str_subparser(subparsers, 'phone')
        add_str_subparser(subparsers, 'city')
        add_str_subparser(subparsers, 'trigram')
        add_str_subparser(subparsers, 'mail')

    elif isinstance(model, Client):
        add_str_subparser(subparsers, 'name')
        add_str_subparser(subparsers, 'phone')
        add_str_subparser(subparsers, 'first_name')
        add_str_subparser(subparsers, 'last_name')
        add_str_subparser(subparsers, 'mail')
        add_list_subparser(subparsers, 'missions', item_type=object_id_checker)

    elif isinstance(model, Vuln):
        add_str_subparser(subparsers, 'name')
        add_str_subparser(subparsers, 'description')
        add_str_subparser(subparsers, 'remediation')
        add_object_subparser(subparsers, 'vuln_type')
        add_object_subparser(subparsers, 'impact')
        add_list_subparser(subparsers, 'host_vulns', item_type=object_id_checker)

    elif isinstance(model, PositivePoint) or isinstance(model, NegativePoint):
        add_str_subparser(subparsers, 'name')
        add_str_subparser(subparsers, 'description')

    elif isinstance(model, Step):
        add_str_subparser(subparsers, 'description')
        add_date_subparser(subparsers, 'find_at')
        add_date_subparser(subparsers, 'created_at')
        add_object_subparser(subparsers, 'mission')

    elif isinstance(model, Host):
        add_str_subparser(subparsers, 'name')
        add_bool_subparser(subparsers, 'checked')
        add_str_subparser(subparsers, 'technology')
        add_object_subparser(subparsers, 'mission')

    elif isinstance(model, HostVuln):
        add_object_subparser(subparsers, 'host')
        add_object_subparser(subparsers, 'vuln')
        add_object_subparser(subparsers, 'impact')
        add_str_subparser(subparsers, 'current_state')

    return parser


class App(Cmd):

    def __init__(self, api):
        super().__init__(
            use_ipython=has_ipython(),
            allow_cli_args=False)

        self.api = api

        self.console = Console()
        self.continuation_prompt = '\x1b[1;31m>>\x1b[0m '
        self.self_in_py = True
        self.context = None

        self.update_prompt()

    @with_argparser(get_show_parser())
    def do_show(self, namespace):
        """
        Print information about one or more object. This command can display the information either in a table or in
        raw.

        If you have a context selected, calling this command without argument will show information about the object
        designated by the current context.
        """

        if namespace.model is None:
            if self.context is None:
                self.console.print('[red]There is no context')
            else:
                if namespace.raw:
                    self.console.print(self.context)
                else:
                    model_name = self.context.__class__.__name__.lower()
                    print_function = self.get_print_function_from_model_name(model_name)

                    print_function([self.context])

            return

        model = self.get_model_from_name(namespace.model)
        ids = namespace.ids

        if namespace.raw:
            print_function = self.console.print
        else:
            print_function = self.get_print_function_from_model_name(namespace.model)

        if len(ids) == 0:
            print_function(model.all(self.api))
        else:
            objects = []

            for id in ids:
                try:
                    objects.append(model.get(self.api, id))
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        self.console.print(f'[yellow]Unable to find an object with id: {id}')
                    else:
                        self.console.print(f'[red]An HTTP error occurred: {e}')

            if len(objects) > 0:
                print_function(objects)
            else:
                self.console.print('Your request returned no object :(')

    @with_argparser(get_use_parser())
    def do_use(self, namespace):
        """
        Change the current context.

        Warning: every unsaved change will be lost.
        """

        model = self.get_model_from_name(namespace.model)
        id = namespace.id

        if id is None:
            self.context = model(id=None)
        else:
            try:
                self.context = model.get(self.api, id)
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    self.console.print(f'[yellow]Unable to find an object with id: {id}')
                else:
                    self.console.print(f'[red]An HTTP error occurred: {e}')

        self.update_prompt()

    @with_argument_list
    def do_assign(self, args):
        """
        Assign a value to a field. The previous value is erased by the next one.

        A field can have one of the following type:
            * string
            * boolean
            * object reference
            * a list of one of the types above

        An object reference must be designated by its identifier (handled internally as a string).

        The syntax for the three atomic types (string, boolean and object reference) is the following:

        ```
        assign <field name> <value>.
        ```

        For the list type the syntax is the following:

        ```
        assign <field name> <add / remove> <space separated list of values>.
        ```

        This command will raise an error if you have no context selected.
        """

        if self.context is None:
            self.console.print('[red]You must enter into a context before setting a field')
            return

        try:
            args = get_assign_parser(self.context).parse_known_args(args)[0]

            if 'action' in args:
                l = getattr(self.context, args.field)

                if args.action == 'add':
                    for e in args.value:
                        if e in l:
                            self.console.print(f'[yellow]The item "{e}" was already added into the field named '
                                               f'"{args.field}"')
                        else:
                            l.append(e)
                else:
                    for e in l:
                        _id = e

                        if issubclass(e.__class__, Model):
                            _id = e.id

                        if _id in args.value:
                            l.remove(e)

                setattr(self.context, args.field, l)
            else:
                setattr(self.context, args.field, args.value)
        except SystemExit:
            # Just ignore the SystemExit exception. The error message is printed by argparse
            pass

    def do_exit(self, _):
        """
        Exit the current context. This command will raise an error if you have no context selected.

        Warning: every unsaved change will be lost.
        """

        if self.context is None:
            self.console.print('[red]You have no context to exit')
        else:
            self.context = None
            self.update_prompt()

    def do_save(self, _):
        """
        Save the object designated by the current context. The object will be either updated or created depending of its
        identifier (`id` field). If the identifier is None, the object is considered new and will be created. Otherwise,
        the object will be updated.

        This command will raise an error if you have no context selected.
        """

        if self.context is None:
            self.console.print('[red]You need to be in a context to save something')
        else:
            try:
                try:
                    self.context = self.context.save(self.api)
                    self.context = self.context.fetch(self.api)
                    self.update_prompt()

                    self.console.print('[green]The object was saved successfully')
                except TypeError:
                    # The user probably tried to save a model containing an object with an undefined id
                    self.console.print('[red]You must set every object identifier before saving')

            except requests.exceptions.HTTPError as e:
                self.console.print(f'[red]Unable to save the object. {e}')

    def do_delete(self, _):
        """
        Delete the object designated by the current context. This command will raise an error if you have no context
        selected or if you try to delete a new object (object identifier is None).
        """

        if self.context is None:
            self.console.print('[red]You must be in a context to delete something')
        elif self.context.id is None:
            self.console.print('[red]You can\'t delete a NEW object')
        else:
            if self.context.delete(self.api):
                self.console.print('[green]The object was deleted successfully')

                self.context = None
                self.update_prompt()
            else:
                self.console.print('[red]An error occurred. Unable to delete the object')

    def update_prompt(self):
        if self.context is None:
            self.prompt = COMMAND_PROMPT.format('')
        else:
            model_name = self.context.__class__.__name__
            id = '\x1b[1;39mNEW\x1b[0m' if (self.context.id is None) else self.context.id

            self.prompt = COMMAND_PROMPT.format(f'-\x1b[0m {model_name}[{id}]\x1b[1;31m ')

    def get_model_from_name(self, model_name):
        return {
            'mission': Mission,
            'user': User,
            'client': Client,
            'vuln': Vuln,
            'positivepoint': PositivePoint,
            'negativepoint': NegativePoint,
            'step': Step,
            'host': Host,
            'impact': Impact,
            'hostvuln': HostVuln
        }[model_name.replace('_', '')]

    def get_print_function_from_model_name(self, model_name):
        return {
            'mission': self.print_missions,
            'user': self.print_users_table,
            'client': self.print_clients_table,
            'vuln': self.print_vulns_table,
            'positivepoint': self.print_points_table,
            'negativepoint': self.print_points_table,
            'step': self.print_steps_table,
            'host': self.print_hosts_table,
            'impact': self.print_impacts_list,
            'hostvuln': self.print_host_vuln
        }[model_name.replace('_', '')]

    @staticmethod
    def get_printable_flag(flag, yes_text='Yes', no_text='No'):
        return f'[green]{yes_text}' if flag else f'[red]{no_text}'

    def print_missions(self, missions):
        if len(missions) > 1:
            self.print_missions_table(missions)
        else:
            self.print_single_mission(missions[0])

    def print_missions_table(self, missions):
        table = Table(box=TABLE_BOX_TYPE)

        table.add_column('ID', justify='center')
        table.add_column('Name', justify='center')
        table.add_column('Duration', justify='center')
        table.add_column('Status', justify='center')
        table.add_column('Nmap', justify='center')
        table.add_column('Nessus', justify='center')
        table.add_column('Hosts', justify='center')

        for mission in missions:
            nmap = self.get_printable_flag(mission.nmap, 'Done', 'To do')
            nessus = self.get_printable_flag(mission.nessus, 'Done', 'To do')
            start_date = date.date_from_iso(mission.start_date)
            end_date = date.date_from_iso(mission.end_date)
            now = datetime.now(timezone.utc)
            _, duration = date.format_delta(end_date, start_date)
            negative, delta = date.format_delta(now, end_date)

            if negative:
                delta = f'[red]Closed {delta} ago[/red]'
            else:
                delta = f'[green]{delta} remaining[/green]'

            table.add_row(mission.id, mission.name, duration, delta, nmap, nessus, str(len(mission.hosts)))

        self.console.print(table)

    def print_single_mission(self, mission):
        layout = Tree(f'#{mission.id} - [bold]{mission.name}[/bold] ({mission.mission_type.name})')
        negative, delta = date.format_delta(datetime.now(timezone.utc), date.date_from_iso(mission.end_date))

        if negative:
            layout.add(f':two-thirty: [red]Closed {delta} ago')
        else:
            layout.add(f':two-thirty: [green]{delta} remaining')

        layout.add(('[green]:heavy_check_mark: ' if mission.nmap else '[yellow]:hourglass_not_done:') + ' Nmap')
        layout.add(('[green]:heavy_check_mark: ' if mission.nessus else '[yellow]:hourglass_not_done:') + ' Nessus')

        if mission.path_to_codi is None:
            layout.add(f':book: [bold red]CodiMD not set')
        else:
            layout.add(f':book: CodiMD > {mission.path_to_codi}')

        if mission.credentials is None:
            layout.add(f':locked_with_key: [bold red]Credentials not set')
        else:
            layout.add(f':locked_with_key: Credentials > {mission.credentials}')

        clients_node = layout.add(':bust_in_silhouette: [blue]Clients[/blue]', guide_style='blue')

        for client in mission.clients:
            if isinstance(client, str):
                clients_node.add(f'[bold]#{client}[/bold] (save to update)')
                continue

            client_node = clients_node.add(f'[bold]{client.first_name} {client.last_name}[/bold] ({client.name})',
                                           guide_style='white')

            client_node.add(client.mail)
            client_node.add(client.phone)

        pentesters_node = layout.add(':robot: [red]Pentesters[/red]', guide_style='red')

        for pentester in mission.users:
            if isinstance(pentester, str):
                pentesters_node.add(f'#{pentester} (save to update)')
                continue

            pentesters_node.add(pentester.username)

        hosts_node = layout.add(':desktop_computer: Scope')

        for host in mission.hosts:
            if isinstance(host, str):
                hosts_node.add(f'#{host} (save to update)')
                continue

            host_node = hosts_node.add(('[green]:heavy_check_mark: ' if host.checked else '[yellow]:hourglass_not_done:') +
                                       f' #{host.id} - {host.name}')

            for host_vuln in host.host_vulns:
                vuln = Vuln.get(self.api, host_vuln.vuln.id)
                impact = host_vuln.impact

                host_node.add(f'#{host_vuln.id} - {vuln.name} ({impact.name}) - {host_vuln.current_state}')

        steps_node = layout.add(':spiral_notepad: [magenta]Activity', guide_style='magenta')

        for step in mission.steps:
            if isinstance(step, str):
                steps_node.add(f'#{step} (save to update)')
                continue

            _, delta = date.format_delta(datetime.now(timezone.utc), date.date_from_iso(step.created_at))

            steps_node.add(f'[bold]{delta} ago[/bold] - #{step.id} - {step.description}')

        self.console.print(layout)

    def get_roles_layout(self, roles):
        layout = Table.grid()
        table = Table(box=TABLE_BOX_TYPE)
        roles_groups = {
            'Client': APIRoles.ROLE_CLIENT_GET_LIST,
            'Host': APIRoles.ROLE_HOST_GET_LIST,
            'HostVuln': APIRoles.ROLE_HOST_VULN_GET_LIST,
            'Impact': APIRoles.ROLE_IMPACT_GET_LIST,
            'Mission': APIRoles.ROLE_MISSION_GET_LIST,
            'MissionType': APIRoles.ROLE_MISSION_TYPE_GET_LIST,
            'NegativePoint': APIRoles.ROLE_NEGATIVE_POINT_GET_LIST,
            'PositivePoint': APIRoles.ROLE_POSITIVE_POINT_GET_LIST,
            'Step': APIRoles.ROLE_STEP_GET_LIST,
            'User': APIRoles.ROLE_USER_GET_LIST,
            'Vuln': APIRoles.ROLE_VULN_GET_LIST,
            'VulnType': APIRoles.ROLE_VULN_TYPE_GET_LIST
        }

        table.add_column('Model name')
        table.add_column('List', justify='center')
        table.add_column('Create', justify='center')
        table.add_column('Read', justify='center')
        table.add_column('Update (full)', justify='center')
        table.add_column('Update (partial)', justify='center')
        table.add_column('Delete', justify='center')

        for model_name, offset in roles_groups.items():
            row = [model_name]

            for i in range(6):
                if roles & (offset << i):
                    row.append('[green]:heavy_check_mark:')
                else:
                    row.append('')

            table.add_row(*row)

        can_upload_host = self.get_printable_flag(roles & APIRoles.ROLE_HOST_UPLOAD)

        layout.add_column()
        layout.add_row(table)
        layout.add_row(f'Can upload host: {can_upload_host}')

        return layout

    def print_users_table(self, users):
        table = Table(box=TABLE_BOX_TYPE, show_lines=True)

        table.add_column('ID', justify='center')
        table.add_column('Name (trigram)', justify='center')
        table.add_column('Phone', justify='center')
        table.add_column('City', justify='center')
        table.add_column('Email', justify='center')
        table.add_column('Enabled', justify='center')
        table.add_column('Roles', justify='center')
        table.add_column('Assigned missions', justify='center')

        for user in users:
            enabled = '[green]Yes' if user.enabled else '[red]No'
            roles_layout = self.get_roles_layout(user.roles_flags)

            if len(user.missions) == 0:
                missions = 'None'
            else:
                missions = ', '.join([mission.id for mission in user.missions])

            if user.trigram is None:
                username = user.username
            else:
                username = f'{user.username} ({user.trigram})'

            table.add_row(user.id, username, user.phone, user.city, user.mail, enabled, roles_layout, missions)

        self.console.print(table)

    def print_clients_table(self, clients):
        table = Table(box=TABLE_BOX_TYPE)

        table.add_column('ID', justify='center')
        table.add_column('Name', justify='center')
        table.add_column('Contact name', justify='center')
        table.add_column('Phone number', justify='center')
        table.add_column('Email address', justify='center')

        for client in clients:
            contact_name = f'{client.first_name} {client.last_name}'

            table.add_row(client.id, client.name, contact_name, client.phone, client.mail)

        self.console.print(table)

    def print_vulns_table(self, vulns):
        table = Table(box=TABLE_BOX_TYPE, show_lines=True)

        table.add_column('ID', justify='center')
        table.add_column('Name', justify='center')
        table.add_column('Description', justify='center')
        table.add_column('Remediation', justify='center')

        for vuln in vulns:
            table.add_row(vuln.id, vuln.name, vuln.description, vuln.remediation)

        self.console.print(table)

    def print_points_table(self, points):
        table = Table(box=TABLE_BOX_TYPE, show_lines=True)

        table.add_column('ID', justify='center')
        table.add_column('Name', justify='center')
        table.add_column('Description', justify='center')

        for point in points:
            table.add_row(point.id, point.name, point.description)

        self.console.print(table)

    def print_steps_table(self, steps):
        table = Table(box=TABLE_BOX_TYPE)

        table.add_column('ID', justify='center')
        table.add_column('Description', justify='center')
        table.add_column('Created', justify='center')
        table.add_column('Found', justify='center')

        for step in steps:
            table.add_row(step.id, step.description, step.created_at, step.find_at)

        self.console.print(table)

    def print_hosts_table(self, hosts):
        table = Table(box=TABLE_BOX_TYPE)

        table.add_column('ID', justify='center')
        table.add_column('Name', justify='center')
        table.add_column('Technology', justify='center')
        table.add_column('Checked', justify='center')
        table.add_column('Vulnerabilities', justify='center')

        for host in hosts:
            checked = self.get_printable_flag(host.checked)

            table.add_row(host.id, host.name, host.technology, checked, str(len(host.host_vulns)))

        self.console.print(table)

    def print_impacts_list(self, impacts):
        tree = Tree('[bold]Impacts')

        for impact in impacts:
            tree.add(f'[bold]#{impact.id}[/bold] - {impact.name}')

        self.console.print(tree)

    def print_host_vuln(self, host_vuln):
        assert(len(host_vuln) == 1)

        host_vuln = host_vuln[0]
        host = vuln = impact = '[bold red]Undefined[/bold red]'

        if host_vuln.host is not None:
            if isinstance(host_vuln.host, str):
                host_object = Host.get(self.api, host_vuln.host)
            else:
                host_object = host_vuln.host.fetch(self.api)

            host = f'[bold]#{host_object.id}[/bold] - {host_object.name}'

        if host_vuln.vuln is not None:
            if isinstance(host_vuln.vuln, str):
                vuln_object = Vuln.get(self.api, host_vuln.vuln)
            else:
                vuln_object = host_vuln.vuln.fetch(self.api)

            vuln = f'[bold]#{vuln_object.id}[/bold] - {vuln_object.name}'

        if host_vuln.impact is not None:
            if isinstance(host_vuln.impact, str):
                impact_object = Impact.get(self.api, host_vuln.impact)
            else:
                impact_object = host_vuln.impact.fetch(self.api)

            impact = f'{impact_object.name}'

        self.console.print(f'{vuln} ({impact}) <=> {host}', highlight=False)


def parse_args():
    parser = argparse.ArgumentParser(description='A command-line client for the SMERSH collaborative pentest tool')

    parser.add_argument('url', type=str, help='The URL of the SMERSH backend server')

    return parser.parse_args()


def print_hello(console):
    # TODO: Replace this by a beautiful ASCII art picture ?
    console.print(Panel(Text('Welcome to the SMERSH Python client', justify='center')))


def main():
    args = parse_args()
    console = Console()
    api = SmershAPI(args.url)

    print_hello(console)

    try:
        while not api.authenticated:
            username = console.input('Enter your username: ')
            password = console.input('Enter your password (will not be echoed): ', password=True)

            try:
                if api.authenticate(username, password):
                    console.print('[green]:heavy_check_mark: Successfully logged in')
                else:
                    console.print('[red]:cross_mark: Unable to log you in. Your credentials seem invalid')
            except requests.exceptions.ConnectionError:
                console.print("[red]Oh no. I can't connect to the specified URL. Please check there is no typo and "
                              "that the host accepts connections. Then try again.")
            except requests.exceptions.HTTPError as e:
                console.print(f'[red]HTTP error {e.response.status_code}: {e}')
    except EOFError:
        # The \n is important because we need to not print inside the input caption
        console.print('\nBye')
        sys.exit(0)

    app = App(api)
    sys.exit(app.cmdloop())


if __name__ == '__main__':
    main()
