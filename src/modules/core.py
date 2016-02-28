import hook
import time

from threading import Thread

@hook.event('PRIVMSG')
def pm(prefix, chan, params):
    if chan == bot.nick and params[0] != '@ezchancmd':
        bot.log('%s: %s' % (prefix[0], ' '.join(params)))

@hook.event('PING')
def ping(prefix, chan, params):
    bot.do('PONG', params[0])

@hook.event('INVITE')
def invited(prefix, chan, params):
    bot.do('JOIN', params[0])

@hook.event('001')
def logged_in(prefix, chan, params):
    bot.nick = chan

    print('Connected to IRC.')

    time.sleep(1)

    if bot.config.get('oper'):
        bot.oper()

    time.sleep(1)

    if bot.config.get('modes'):
        bot.do('MODE', bot.nick, bot.config.get('modes'))

    bot.join(bot.config.get('chans'))

@hook.event('NICK')
def nick_changed(prefix, chan, params):
    if prefix[0] == bot.nick:
        bot.nick = chan

@hook.event('JOIN')
def bot_joined(prefix, destination, params):
    if prefix[0] == bot.nick:
        bot.chans.append(params[0])

        if params[0] not in bot.config.getd('chans'):
            bot.config.append('chans', params[0])

@hook.event('PART')
def bot_parted(prefix, destination, params):
    if prefix[0] == bot.nick:
        bot.chans.remove(destination)

        bot.config.remove('chans', destination)

@hook.event('KICK')
def bot_kicked(prefix, destination, params):
    if params[0] == bot.nick:
        bot.chans.remove(destination)

        bot.config.remove('chans', destination)
