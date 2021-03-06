"""
.. module:: IRCCore
   :synopsis: IRC protocol class

.. moduleauthor:: Dave Pedu <dave@davepedu.com>

"""

import socket
import asyncio
import logging
import traceback
import sys
from inspect import getargspec
from time import sleep
from collections import namedtuple
from io import StringIO

IRCEvent = namedtuple("IRCEvent", "command args prefix trailing")
UserPrefix = namedtuple("UserPrefix", "nick username hostname")
ServerPrefix = namedtuple("ServerPrefix", "hostname")


class IRCCore(object):

    def __init__(self, servers):

        self.connected = False
        """If we're connected or not"""

        self.log = logging.getLogger('IRCCore')
        """Reference to logger object"""

        self.buffer = StringIO()
        """cStringIO used as a buffer"""

        self.alive = True
        """True if we should try to stay connected"""

        self.server = 0
        """Current server index"""
        self.servers = servers
        """List of server address"""
        self.port = 0
        """Server port"""
        self.connection_family = socket.AF_UNSPEC
        """Socket family. 0 will auto-detect ipv4 or v6. Change this to socket.AF_INET or socket.AF_INET6 force use of
           ipv4 or ipv6."""

        self.bind_addr = None
        """Optionally bind to a specific address. This should be a (host, port) tuple."""

        # Set up hooks for modules
        self.initHooks()

    async def loop(self, loop):
        while self.alive:
            try:
                # TODO support ipv6 again
                self.reader, self.writer = await asyncio.open_connection(self.servers[self.server][0],
                                                                         port=self.servers[self.server][1],
                                                                         loop=loop,
                                                                         ssl=None,
                                                                         family=self.connection_family,
                                                                         local_addr=self.bind_addr)
                self.fire_hook("_CONNECT")
            except (socket.gaierror, ConnectionRefusedError):
                traceback.print_exc()
                logging.warning("Non-fatal connect error, trying next server...")
                self.server = (self.server + 1) % len(self.servers)
                await asyncio.sleep(1, loop=loop)
                continue

            while self.alive:
                try:
                    data = await self.reader.readuntil()
                    self.log.debug("<<< {}".format(repr(data)))
                    self.process_line(data.decode("UTF-8"))
                except (ConnectionResetError, asyncio.streams.IncompleteReadError):
                    traceback.print_exc()
                    break
                except (UnicodeDecodeError, ):
                    traceback.print_exc()
            self.fire_hook("_DISCONNECT")
            self.writer.close()
            if self.alive:
                # TODO ramp down reconnect attempts
                logging.info("Reconnecting in 3s...")
                await asyncio.sleep(3)

    async def kill(self, message="Help! Another thread is killing me :("):
        """Send quit message, flush queue, and close the socket

        :param message: Quit message to send before disconnecting
        :type message: str
        """
        self.alive = False
        self.act_QUIT(message)  # TODO will this hang if the socket is having issues?
        await self.writer.drain()
        self.writer.close()
        self.log.info("Kill complete")

    def process_line(self, data):
        """Process one line of text irc sent us

        :param data: the data to process
        :type data: str"""
        if data.strip() == "":
            return

        prefix = None
        command = None
        args = []
        trailing = None

        if data[0] == ":":
            prefix = data.split(" ")[0][1:]
            data = data[data.find(" ") + 1:]
        command = data.split(" ")[0]
        data = data[data.find(" ") + 1:]
        if(data[0] == ":"):
            # no args
            trailing = data[1:].strip()
        else:
            trailing = data[data.find(" :") + 2:].strip()
            data = data[:data.find(" :")]
            args = data.split(" ")
        for index, arg in enumerate(args):
            args[index] = arg.strip()

        self.fire_hook("_RECV", args=args, prefix=prefix, trailing=trailing)
        if command not in self.hookcalls:
            self.log.warning("Unknown command: cmd='%s' prefix='%s' args='%s' trailing='%s'" % (command, prefix, args,
                                                                                                trailing))
        else:
            self.fire_hook(command, args=args, prefix=prefix, trailing=trailing)

    def sendRaw(self, data):
        self.log.debug(">>> {}".format(repr(data)))
        self.fire_hook('_SEND', args=None, prefix=None, trailing=None)
        self.writer.write((data + "\r\n").encode("UTF-8"))

    " Module related code "
    def initHooks(self):
        """Defines hooks that modules can listen for events of"""
        self.hooks = [
            '_CONNECT',
            '_DISCONNECT',
            '_RECV',
            '_SEND',
            'NOTICE',
            'MODE',
            'PING',
            'JOIN',
            'QUIT',
            'NICK',
            'PART',
            'PRIVMSG',
            'KICK',
            'INVITE',
            '001',
            '002',
            '003',
            '004',
            '005',
            '250',
            '251',
            '252',
            '254',
            '255',
            '265',
            '266',
            '332',
            '333',
            '353',
            '366',
            '372',
            '375',
            '376',
            '422',
            '433',
        ]
        " mapping of hooks to methods "
        self.hookcalls = {command: [] for command in self.hooks}

    def fire_hook(self, command, args=None, prefix=None, trailing=None):
        """Run any listeners for a specific hook

        :param command: the hook to fire
        :type command: str
        :param args: the list of arguments, if any, the command was passed
        :type args: list
        :param prefix: prefix of the sender of this command
        :type prefix: str
        :param trailing: data payload of the command
        :type trailing: str"""
        for hook in self.hookcalls[command]:
            try:
                if len(getargspec(hook).args) == 2:
                    hook(IRCCore.packetAsObject(command, args, prefix, trailing))
                else:
                    hook(args, prefix, trailing)

            except:
                self.log.warning("Error processing hook: \n%s" % self.trace())

    def addHook(self, command, method):
        """**Internal.** Enable (connect) a single hook of a module

        :param command: command this hook will trigger on
        :type command: str
        :param method: callable method object to hook in
        :type method: object"""
        " add a single hook "
        if command in self.hooks:
            self.hookcalls[command].append(method)
        else:
            self.log.warning("Invalid hook - %s" % command)
            return False

    def removeHook(self, command, method):
        """**Internal.** Disable (disconnect) a single hook of a module

        :param command: command this hook triggers on
        :type command: str
        :param method: callable method that should be removed
        :type method: object"""
        " remove a single hook "
        if command in self.hooks:
            for hookedMethod in self.hookcalls[command]:
                if hookedMethod == method:
                    self.hookcalls[command].remove(hookedMethod)
        else:
            self.log.warning("Invalid hook - %s" % command)
            return False

    def packetAsObject(command, args, prefix, trailing):
        """Given an irc message's args, prefix, and trailing data return an object with these properties

        :param args: list of args from the IRC packet
        :type args: list
        :param prefix: prefix object parsed from the IRC packet
        :type prefix: ServerPrefix or UserPrefix
        :param trailing: trailing data from the IRC packet
        :type trailing: str
        :returns: object -- a IRCEvent object with the ``args``, ``prefix``, ``trailing``"""

        return IRCEvent(command, args,
                        IRCCore.decodePrefix(prefix) if prefix else None,
                        trailing)

    " Utility methods "
    @staticmethod
    def decodePrefix(prefix):
        """Given a prefix like nick!username@hostname, return an object with these properties

        :param prefix: the prefix to disassemble
        :type prefix: str
        :returns: object -- an UserPrefix object with the properties `nick`, `username`, `hostname` or a ServerPrefix
        object with the property `hostname`
        """
        if "!" in prefix:
            nick, prefix = prefix.split("!")
            username, hostname = prefix.split("@")
            return UserPrefix(nick, username, hostname)
        else:
            return ServerPrefix(prefix)

    @staticmethod
    def trace():
        """Return the stack trace of the bot as a string"""
        return traceback.format_exc()

    @staticmethod
    def fulltrace():
        """Return the stack trace of the bot as a string"""
        result = ""
        result += "\n*** STACKTRACE - START ***\n"
        code = []
        for threadId, stack in sys._current_frames().items():
            code.append("\n# ThreadID: %s" % threadId)
            for filename, lineno, name, line in traceback.extract_stack(stack):
                code.append('File: "%s", line %d, in %s' % (filename, lineno, name))
                if line:
                    code.append("  %s" % (line.strip()))
        for line in code:
            result += line + "\n"
        result += "\n*** STACKTRACE - END ***\n"
        return result

    " Data Methods "
    def get_nick(self):
        """Get the bot's current nick

        :returns: str - the bot's current nickname"""
        return self.nick

    " Action Methods "
    def act_PONG(self, data):
        """Use the `/pong` command - respond to server pings

        :param data: the string or number the server sent with it's ping
        :type data: str"""
        self.sendRaw("PONG :%s" % data)

    def act_USER(self, username, hostname, realname):
        """Use the USER protocol command. Used during connection

        :param username: the bot's username
        :type username: str
        :param hostname: the bot's hostname
        :type hostname: str
        :param realname: the bot's realname
        :type realname: str"""
        self.sendRaw("USER %s %s %s :%s" % (username, hostname, self.servers[self.server], realname))

    def act_NICK(self, newNick):
        """Use the `/nick` command

        :param newNick: new nick for the bot
        :type newNick: str"""
        self.nick = newNick
        self.sendRaw("NICK %s" % newNick)

    def act_JOIN(self, channel):
        """Use the `/join` command

        :param channel: the channel to attempt to join
        :type channel: str"""
        self.sendRaw("JOIN %s" % channel)

    def act_PRIVMSG(self, towho, message):
        """Use the `/msg` command

        :param towho: the target #channel or user's name
        :type towho: str
        :param message: the message to send
        :type message: str"""
        self.sendRaw("PRIVMSG %s :%s" % (towho, message))

    def act_MODE(self, channel, mode, extra=None):
        """Use the `/mode` command

        :param channel: the channel this mode is for
        :type channel: str
        :param mode: the mode string. Example: +b
        :type mode: str
        :param extra: additional argument if the mode needs it. Example: user@*!*
        :type extra: str"""
        if extra is not None:
            self.sendRaw("MODE %s %s %s" % (channel, mode, extra))
        else:
            self.sendRaw("MODE %s %s" % (channel, mode))

    def act_ACTION(self, channel, action):
        """Use the `/me <action>` command

        :param channel: the channel name or target's name the message is sent to
        :type channel: str
        :param action: the text to send
        :type action: str"""
        self.sendRaw("PRIVMSG %s :\x01ACTION %s" % (channel, action))

    def act_KICK(self, channel, who, comment=""):
        """Use the `/kick <user> <message>` command

        :param channel: the channel from which the user will be kicked
        :type channel: str
        :param who: the nickname of the user to kick
        :type action: str
        :param comment: the kick message
        :type comment: str"""
        self.sendRaw("KICK %s %s :%s" % (channel, who, comment))

    def act_QUIT(self, message):
        """Use the `/quit` command

        :param message: quit message
        :type message: str"""
        self.sendRaw("QUIT :%s" % message)

    def act_PASS(self, password):
        """
        Send server password, for use on connection
        """
        self.sendRaw("PASS %s" % password)
