# DissBot
A fast, lightweight, flexible and easily customisable IRC bot.

##setting up

1. Install dependencies: `$ python setup.py`

2. Configure `config.json` to suit your needs.

3. Run: `$ python3 src/main.py`

##extending

Modules are kept in the `src/modules` directory. Simply add a new python file and write your commands or events:

    import hook

    @hook.command('example')
    def example(prefix, chan, params):

        # the prefix parameter contains the sender's info
        nick, ident, host = prefix

        # functions can be accessed through the bot global variable
        bot.say(chan, 'Hi %s!' % nick)


    @hook.event('PRIVMSG')
    def echo(prefix, chan, params):
        bot.say(chan, ' '.join(params))

You can use the `reload` command to reload all modules and config. I suggest you have a look through `modules/admin.py` to view the default commands.
