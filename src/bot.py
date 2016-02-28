import re
import os
import sys
import ssl
import glob
import time
import style
import socket
import fnmatch
import traceback

from queue import Queue
from config import Config
from threading import Thread

class DissBot():
    debug = False

    socket = None
    connected = False

    iqueue = Queue()
    oqueue = Queue()

    waiting = []

    config = Config('config.json')

    events = {}
    commands = {}

    load_time = 0
    start_time = 0

    ibuffer = ''
    obuffer = b''

    nick = ''
    chans = []

    flood_check = {}

    def __init__(self):
        if not self.load():
            sys.exit('Exiting...')

        self.connect()

        self.thread(self.send_loop)
        self.thread(self.parse_loop)

    def thread(self, func, args=()):
        return Thread(target=func, args=args).start()

    def load(self):
        self.load_time = time.time()

        print('Loading config...')

        try:
            self.config.load()

        except:
            traceback.print_exc()
            print('ERROR: failed to load %s' % self.config.filename)
            return False

        print('Loading modules...')

        self.commands = {}
        self.events = {}

        filename = ''

        try:
            files = set(glob.glob(os.path.join('modules', '*.py')))

            for file in files:
                filename = file

                with open(file, 'r') as fp:
                    code = compile(fp.read(), file, 'exec')

                namespace = {'bot': self}

                eval(code, namespace)

                commands = []
                events = []

                for obj in namespace.values():
                    if hasattr(obj, '_command'):
                        for command in obj._command:
                            if command not in self.commands:
                                self.commands[command] = []

                            self.commands[command].append(obj)

                    if hasattr(obj, '_event'):
                        for event in obj._event:
                            if event not in self.events:
                                self.events[event] = []

                            self.events[event].append(obj)

                print('Module loaded: %s' % file)

        except:
            traceback.print_exc()
            print('ERROR: failed to load module (%s)' % filename)

        print('Successfully loaded.')
        return True

    def parse(self, params, *args):
        values = []
        args = list(args)

        if len(args) > len(params):
            params += [None] * (len(args) - len(params))

        for param, arg in zip(params, args):
            if param == None and arg is Exception:
                raise Exception('Invalid params')

            values.append(param if param != None else arg)

        return tuple(values) if len(values) > 1 else values[0]

    def die(self):
        self.disconnect()
        self.iqueue.put('')

    def disconnect(self):
        if self.connected:
            self.connected = False
            self.do('QUIT')
            self.socket.close()

    def connect(self):
        print('Connecting to IRC...')

        self.start_time = time.time()

        ip = socket.AF_INET6 if self.config.get('ipv6') else socket.AF_INET

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.socket = ssl.wrap_socket(s) if self.config.get('ssl') else s

        self.socket.connect((self.config.get('server', ''), self.config.get('port', 6667)))

        if self.config.get('pass'):
            self.send('PASS %s' % self.config.get('pass', ''))

        self.send('NICK %s' % self.config.get('nick', 0))

        self.send('USER %s 3 * :%s' % (
            self.config.get('ident', 'DissBot'),
            self.config.get('realname', 'DissBot')
        ))

        self.connected = True

        self.thread(self.recv_loop)

    def command(self, func, chan, prefix, nick, ident, host, params):
        # must or must not be a PM
        if hasattr(func, '_pm'):
            if getattr(func, '_pm'):
                if chan.startswith('#'):
                    return

            elif not chan.startswith('#'):
                return

        # must be performed in specific channel
        if hasattr(func, '_channel'):
            chanlist = getattr(func, '_channel')

            if not isinstance(chanlist, list):
                chanlist = [chanlist]

            if chan not in chanlist:
                return

        where = chan

        divert = self.config.get('divert', {})

        # command can or must be diverted
        if hasattr(func, '_divert'):
            if chan in divert:
                where = divert[chan]

            if where not in self.chans:
                return

        if hasattr(func, '_control'):
            if not chan in divert or where not in self.chans:
                return

        # admin perm overrides all
        admin = self.config.get(['perms', 'admin'], {})

        if self.match(admin, prefix):
            pass

        # user must have permission, overrides flags
        elif hasattr(func, '_perm'):
            perm = getattr(func, '_perm')

            if perm not in self.config.get('perms', {}):
                return

            if not self.match(self.config.get('perms', {})[perm], prefix):
                return

        # user must have specific flag(s)
        elif hasattr(func, '_flags'):
            flags = getattr(func, '_flags')

            response = self.wait('WHO %s' % where, '352', end='315')

            if response:
                has_flag = False

                for person in response:
                    w_prefix, w_chan, w_params = person

                    if len(w_params) < 8: return

                    if w_params[4] == nick and w_params[0] == chan:
                        for perm in flags:
                            if perm in w_params[5]:
                                has_flag = True

                                break

                if not has_flag: return

            else: return

        self.thread(func, args=((nick, ident, host), where, params))

    # loops
    def parse_loop(self):
        while self.connected:
            msg = self.iqueue.get()

            if msg == StopIteration:
                self.connect()
                continue

            if self.debug and msg: print(msg)

            regex = re.compile(r'(?::(([^@! ]+)!?([^@ ]+)?@?([^ ]+)?))? ?([^ ]+) ?([^: ]*) :?(.*)?')

            try:
                prefix, nick, ident, host, type, chan, message = re.findall(regex, msg)[0]

            except: continue

            message = style.remove(message)

            params = re.findall(r'(?<=")\w[^"]+(?=")|[^" ]+', message)

            # do response waiting
            for waiting in self.waiting:
                if type in waiting['keys']:
                    if waiting['prefix'] and not self.match(waiting['prefix'], prefix):
                        continue
                    if waiting['chan'] and not self.match(waiting['chan'], chan):
                        continue
                    if waiting['message'] and not self.match(waiting['message'], message):
                        continue

                    waiting['values'].append([(nick, ident, host), chan, params])

                    if type not in waiting['end']: break

                if type in waiting['end'] and waiting['values']:
                    self.waiting.remove(waiting)

                    break

            # do events

            if type in self.events:
                for func in self.events[type]:
                    # must be performed in specific channel
                    if hasattr(func, '_channel'):
                        if getattr(func, '_channel') != chan:
                            continue

                    self.thread(func, ((nick, ident, host), chan, params))

            # do commands
            if type == 'PRIVMSG' and params and params[0].startswith(self.config.get('prefix', '$')):
                command = params[0][1:]

                params.pop(0)

                ignore = self.config.get('ignore', [])

                if command in self.commands and not self.match(ignore, prefix):
                    if chan != self.config.get('log'):
                        self.log('%s %s called by %s in %s (%s)' % (
                            style.color('Command:', style.GREEN),
                            command,
                            nick,
                            chan,
                            ', '.join(params)
                            ))

                    if chan == self.nick:
                        chan = nick

                    for func in self.commands[command]:
                        self.thread(self.command, (func, chan, prefix, nick, ident, host, params))

        print('Exited parse loop.')

    def recv_loop(self):
        recv_time = time.time()

        while self.connected:
            try:
                data = self.socket.recv(4096)

                self.ibuffer += data.decode()

                if data:
                    recv_time = time.time()

                else:
                    if time.time() - recv_time > self.config.get('timeout', 60):
                        self.iqueue.put(StopIteration)
                        self.socket.close()
                        break

                    time.sleep(1)

            except:
                time.sleep(1)
                continue

            while '\r\n' in self.ibuffer:
                line, self.ibuffer = self.ibuffer.split('\r\n', 1)

                self.iqueue.put(line)

        print('Exited recv loop.')

    def send_loop(self):
        while self.connected:
            line = self.oqueue.get().splitlines()[0][:1020]

            self.obuffer += line.encode('utf-8', 'replace') + b'\r\n'

            while self.obuffer:
                try:
                    sent = self.socket.send(self.obuffer)
                    self.obuffer = self.obuffer[sent:]

                except: break

            self.oqueue.task_done()

        print('Exited send loop.')

    def wait(self, send, events, end=[], prefix=False, chan=False, message=False):
        if not isinstance(events, list):
            events = [events]

        if not isinstance(end, list):
            end = [end]

        response = {
            'end': end if end else events,
            'keys': events,
            'values': [],
            'prefix': prefix,
            'chan': chan,
            'message': message
        }

        self.waiting.append(response)
        self.send(send)

        seconds = 4

        while response in self.waiting and seconds:
            seconds -= 0.5
            time.sleep(0.5)

        if not seconds:
            if response in self.waiting:
                self.waiting.remove(response)

            return False

        return response['values']

    def time(self, str):
        seconds = 0

        for match in re.findall(r'(([0-9]+)([wdhms]))', str):
            if match[2] == 'w':
                seconds += int(match[1]) * (60 * 60 * 24 * 7)
            if match[2] == 'd':
                seconds += int(match[1]) * (60 * 60 * 24)
            if match[2] == 'h':
                seconds += int(match[1]) * (60 * 60)
            if match[2] == 'm':
                seconds += int(match[1]) * 60
            if match[2] == 's':
                seconds += int(match[1])

        return seconds

    def match(self, patterns, strings, retpat=True):
        if not isinstance(patterns, list):
            patterns = [patterns]
        if not isinstance(strings, list):
            strings = [strings]

        matches = []

        if retpat:
            for str in strings:
                matches.extend([n for n in patterns if fnmatch.fnmatch(str, n)])
        else:
            for pattern in patterns:
                matches.extend([n for n in strings if fnmatch.fnmatch(n, pattern)])

        return matches

    # irc actions
    def join(self, chans):
        if not isinstance(chans, list):
            chans = [chans]

        for chan in chans:
            print('JOIN', chan)
            self.do('JOIN', chan)

    def part(self, chans):
        if not isinstance(chans, list):
            chans = [chans]

        for chan in chans:
            print('PART', chan)
            self.do('PART', chan)

    def oper(self):
        if self.config.get('oper_name') and self.config.get('oper_pass'):
            self.do('OPER', self.config.get('oper_name'), self.config.get('oper_pass'))

    # output
    def log(self, text):
        if self.config.get('log', False):
            self.say(self.config.get('log'), text)

        print(style.remove(text))

    def say(self, targets, text, notice=False, flood=True):
        if not isinstance(targets, list):
            targets = [targets]

        for target in targets:
            mode = 'NOTICE' if notice else 'PRIVMSG'

            if not flood:
                self.do(mode, target, text)
                return

            if target not in self.flood_check:
                self.flood_check[target] = [time.time(), 0]

            diff = time.time() - self.flood_check[target][0]
            delay = self.config.get('flood_delay', 0.2)
            limit = self.config.get('flood_limit', 10)

            if diff < delay:
                self.flood_check[target][1] += 1
            else:
                self.flood_check[target][1] -= min(int(diff / delay), self.flood_check[target][1])

            self.flood_check[target][0] = time.time()

            if self.flood_check[target][1] >= limit:
                if self.flood_check[target][1] == limit:
                    self.log('Flood triggered in %s.' % target)
                    self.say(target, 'Flood triggered.', flood=False)

            else: self.do(mode, target, text)

    def ctcp(self, target, ctcp, text):
        self.do('PRIVMSG', target, '\x01%s %s\x01' % (ctcp, text))

    def do(self, command, *args):
        msg = ' '.join(args)
        max = 510 - (len(command) + 1)

        lines = [msg[i:i+max] for i in range(0, len(msg), max)]

        for line in lines:
            self.send(command + ' ' + line)

    def send(self, str):
        self.oqueue.put(str)
