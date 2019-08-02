#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
if sys.version_info[0] < 3:
    raise Exception("Must be using Python 3.")

from telegram.ext import Updater, CommandHandler, Job, MessageHandler, Filters
from telegram import Bot
import logging
from datetime import datetime, timezone, timedelta
import datetime as dt
import time
import os
import errno
import json
import threading
import fnmatch
import DataSources
import Preferences
import copy
from time import sleep
from geopy.geocoders import Nominatim
import geopy
from geopy.distance import VincentyDistance

from instructions import help_text_1, start_text

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)
prefs = Preferences.UserPreferences()
jobs = dict()
geolocator = Nominatim()

# Variables - Empty dicts
sent = dict()
locks = dict()
search_ids = dict()
pokemon_name = dict()
move_name = dict()

location_radius = 1
# Mysql data
thismodule = sys.modules[__name__]


# Command-functions
def cmd_help(bot, update):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    logger.info('[%s@%s] Sending help text.' % (userName, chat_id))

    bot.sendMessage(chat_id, help_text_1, parse_mode='Markdown')


def cmd_start(bot, update, job_queue):
    chat_id = update.message.chat_id
    userName = update.message.from_user.first_name

    logger.info('[%s@%s] Starting.' % (userName, chat_id))

    bot.sendMessage(chat_id, start_text % (userName), parse_mode='Markdown')

    # Set defaults and location
    pref = prefs.get(chat_id)
    checkAndSetUserDefaults(pref, bot, chat_id)

    addJob(bot, update, job_queue)
    logger.info('[%s@%s] Started the Bot.' % (userName, chat_id))


def cmd_SwitchVenue(bot, update):

    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    # Lade User Einstellungen
    pref = prefs.get(chat_id)

    if pref['user_send_venue'] == 0:
        pref.set('user_send_venue', 1)
        bot.sendMessage(chat_id, text='Pokéstops werden nun in einer Nachricht gesendet')
    else:
        pref.set('user_send_venue', 0)
        bot.sendMessage(chat_id, text='Pokéstops werden nun in zwei Nachrichten gesendet')

    logger.info('[%s@%s] Switched message style' % (userName, chat_id))


def cmd_status(bot, update):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    # Lade User Einstellungen
    pref = prefs.get(chat_id)

    loc = pref.get('location')
    lat = loc[0]
    lon = loc[1]
    radius = "Kein Radius"

    if lat is not None and loc[2] is not None:
        radius = float(loc[2])*1000

    prefmessage = "*Einstellungen:*\n" + \
    "Standort: %s,%s\nRadius: %s m" % (lat, lon, radius)

    commandmessage = "/standort %s,%s\n/radius %s" % (lat, lon, radius)

    bot.sendMessage(chat_id, text='%s' % (prefmessage), parse_mode='Markdown')
    bot.sendMessage(chat_id, text='%s' % (commandmessage), parse_mode='Markdown')


def cmd_clear(bot, update):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    pref = prefs.get(chat_id)

    #Removes the job if the user changed their mind
    logger.info('[%s@%s] Clear list.' % (userName, chat_id))

    if chat_id not in jobs:
        bot.sendMessage(chat_id, text='Du hast keinen aktiven Scanner! Bitte verwende /start um den Bot zu starten.')
        return

    # Remove from jobs
    job = jobs[chat_id]
    job.schedule_removal()
    #job.stop()
    del jobs[chat_id]

    # Remove from sent
    del sent[chat_id]
    # Remove from locks
    del locks[chat_id]

    pref.reset_user()

    bot.sendMessage(chat_id, text='Benachrichtigungen erfolgreich entfernt!')


def cmd_save(bot, update):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    pref = prefs.get(chat_id)
    usage_message = 'Du hast keinen aktiven Scanner! Bitte verwende /start und sende deinen Standort.'
    logger.info('[%s@%s] Save.' % (userName, chat_id))

    if chat_id not in jobs:
        bot.sendMessage(chat_id, text=usage_message)
        return
    pref.set_preferences()
    bot.sendMessage(chat_id, text='Speichern erfolgreich!')


def cmd_saveSilent(bot, update):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    pref = prefs.get(chat_id)
    usage_message = 'Du hast keinen aktiven Scanner! Bitte verwende /start und sende deinen Standort.'
    logger.info('[%s@%s] Save.' % (userName, chat_id))

    if chat_id not in jobs:
        bot.sendMessage(chat_id, text=usage_message)
        return
    pref.set_preferences()


def cmd_load(bot, update, job_queue):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    pref = prefs.get(chat_id)
    usage_message = 'Du hast keine gespeicherten Einstellungen!'
    logger.info('[%s@%s] Attempting to load.' % (userName, chat_id))

    r = pref.load()
    if r is None:
        bot.sendMessage(chat_id, text=usage_message)
        return

    if not r:
        bot.sendMessage(chat_id, text='Bereits aktuell')
        return
    else:
        bot.sendMessage(chat_id, text='Laden erfolgreich!')

    # We might be the first user and above failed....
    addJob(bot, update, job_queue)
    send_venue = pref.get('user_send_venue')
    loc = pref.get('location')
    lat = loc[0]
    lon = loc[1]

    # Send Settings to user and save to json file
    checkAndSetUserDefaults(pref, bot, chat_id)
    cmd_saveSilent(bot, update)
    cmd_status(bot, update)


def cmd_load_silent(bot, chat_id, job_queue):
    userName = ''

    pref = prefs.get(chat_id)

    #logger.info('[%s@%s] Automatic load.' % (userName, chat_id))
    r = pref.load()
    if r is None:
        return

    if not r:
        return

    # We might be the first user and above failed....
    addJob_silent(bot, chat_id, job_queue)
    send_venue = pref.get('user_send_venue')
    loc = pref.get('location')
    lat = loc[0]
    lon = loc[1]

    checkAndSetUserDefaults(pref, bot, chat_id)


def cmd_location(bot, update):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    if update.message.chat.type != 'private':
        return

    pref = prefs.get(chat_id)
    usage_message = 'Du hast keinen aktiven Scanner! Bitte verwende /start und sende deinen Standort.'

    if chat_id not in jobs:
        bot.sendMessage(chat_id, text=usage_message)
        return

    user_location = update.message.location
    location_radius = pref['location'][2]

    # We set the location from the users sent location.
    pref.set('location', [user_location.latitude, user_location.longitude, location_radius])

    logger.info('[%s@%s] Setting scan location to Lat %s, Lon %s, R %s' % (userName, chat_id,
        pref['location'][0], pref['location'][1], pref['location'][2]))

    # Send confirmation nessage
    location_url = ('https://www.freemaptools.com/radius-around-point.htm?clat=%f&clng=%f&r=%f&lc=FFFFFF&lw=1&fc=00FF00&mt=r&fs=true&nomoreradius=true'
        % (pref['location'][0], pref['location'][1], pref['location'][2]))
    bot.sendMessage(chat_id, text="Setze Standort auf: %f / %f mit Radius %.2f m" %
        (pref['location'][0], pref['location'][1], 1000*pref['location'][2]))
    bot.sendMessage(chat_id, text="Deinen Radius kannst du hier sehen:\n\n" + location_url, disable_web_page_preview="True")


def cmd_location_str(bot, update, args, job_queue):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    pref = prefs.get(chat_id)
    location_radius = pref['location'][2]
    usage_message = 'Du hast keinen aktiven Scanner! Bitte verwende /start und sende deinen Standort.'

    if chat_id not in jobs:
        bot.sendMessage(chat_id, text=usage_message)
        return

    if len(args) <= 0:
        bot.sendMessage(chat_id, text='You have not supplied a location')
        return

    try:
        user_location = geolocator.geocode(' '.join(args), timeout=10)
    except Exception as e:
        logger.error('[%s@%s] %s' % (userName, chat_id, repr(e)))
        bot.sendMessage(chat_id, text='Standort nicht gefunden oder Openstreetmap ist down! Bitte versuche es erneut damit der Bot startet!')
        return

    # We set the location from the users sent location.
    pref.set('location', [user_location.latitude, user_location.longitude, location_radius])

    logger.info('[%s@%s] Setting scan location to Lat %s, Lon %s, R %s' % (userName, chat_id,
        pref['location'][0], pref.preferences['location'][1], pref.preferences['location'][2]))

    # Send confirmation nessage
    location_url = ('https://www.freemaptools.com/radius-around-point.htm?clat=%f&clng=%f&r=%f&lc=FFFFFF&lw=1&fc=00FF00&mt=r&fs=true&nomoreradius=true'
        % (pref['location'][0], pref['location'][1], pref['location'][2]))
    bot.sendMessage(chat_id, text="Setze Standort auf: %f / %f mit Radius %.2f m" %
        (pref['location'][0], pref['location'][1], 1000*pref['location'][2]))
    bot.sendMessage(chat_id, text="Deinen Radius kannst du hier sehen:\n\n" + location_url, disable_web_page_preview="True")


def cmd_radius(bot, update, args):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username

    pref = prefs.get(chat_id)
    usage_message = 'Du hast keinen aktiven Scanner! Bitte verwende /start und sende deinen Standort.'

    if chat_id not in jobs:
        bot.sendMessage(chat_id, text=usage_message)
        return

    # Check if user has set a location
    user_location = pref.get('location')

    if user_location[0] is None:
        bot.sendMessage(chat_id, text="Du hast keinen Standort eingestellt. Bitte mache dies zuerst!")
        return

    # Get the users location
    logger.info('[%s@%s] Retrieved Location as Lat %s, Lon %s, R %s (Km)' % (
    userName, chat_id, user_location[0], user_location[1], user_location[2]))

    if args != []:
        if args[0].isdigit():
            if len(args) < 1:
                bot.sendMessage(chat_id, text="Aktueller Standort ist: %f / %f mit Radius %.2f m"
                    % (user_location[0], user_location[1], user_location[2]))
        else:
            bot.sendMessage(chat_id, text='Bitte nur Zahlenwerte eingeben!')
            return
    else:
        bot.sendMessage(chat_id, text='Bitte nur Zahlenwerte eingeben!')
        return

    # Change the radius
    if float(args[0]) > 10000:
        args[0] = 10000
        bot.sendMessage(chat_id, text='Dein Radius ist größer als 10km! Er wird auf 10km gestellt.')
    try:
        radius = float(args[0])
        pref.set('location', [user_location[0], user_location[1], radius/1000])

        logger.info('[%s@%s] Set Location as Lat %s, Lon %s, R %s (Km)' % (userName, chat_id, pref['location'][0],
            pref['location'][1], pref['location'][2]))

        # Send confirmation
        location_url = ('https://www.freemaptools.com/radius-around-point.htm?clat=%f&clng=%f&r=%f&lc=FFFFFF&lw=1&fc=00FF00&mt=r&fs=true&nomoreradius=true' % (pref['location'][0], pref['location'][1], pref['location'][2]))
        bot.sendMessage(chat_id, text="Setze Standort auf: %f / %f mit Radius %.2f m" % (pref['location'][0],
            pref['location'][1], 1000*pref['location'][2]))
        bot.sendMessage(chat_id, text="Deinen Radius kannst du hier sehen:\n\n" + location_url, disable_web_page_preview="True")

    except Exception as e:
        logger.error('[%s@%s] %s' % (userName, chat_id, repr(e)))
        bot.sendMessage(chat_id, text='Radius nicht zulässig! Bitte Zahl eingeben!')
        return


def cmd_unknown(bot, update):
    chat_id = update.message.chat_id
    if update.message.text and update.message.chat.type == 'private':
        bot.send_message(chat_id, text="Falsche Eingabe. Ich habe dich nicht verstanden!\nSchaue am besten in der Hilfe nach: /help")


def error(bot, update, error):
    logger.warn('Update "%s" caused error "%s"' % (update, error))


def checkAndSetUserDefaults(pref, bot, chat_id):

    loc = pref.get('location')
    if loc[0] is None or loc[1] is None:
        map_location = config.get('MAP_LOCATION', '0.0, 0.0').split(',')
        location_message = '*Du hast keinen Standort gewählt! Du wirst nun nach %s, %s gesetzt!*' % (map_location[0], map_location[1])
        pref.set('location', [float(map_location[0]), float(map_location[1]), 0.1])
        #pref.set('location', [1.0, 2.0, 1])
        logger.info(pref.get('location'))
        bot.sendMessage(chat_id, text=location_message, parse_mode='Markdown')
        loc = pref.get('location')
        logger.info(loc)
    if loc[2] is None:
        pref.set('location', [loc[0], loc[1], 0.1])
    if loc[2] is not None and float(loc[2]) > 10:
        pref.set('location', [loc[0], loc[1], 10])


def getMysqlData(bot, job):
    logger.info('Getting MySQLdata...')
    thismodule.pokemon_db_data = dataSource.getPokemonData()
    return thismodule.pokemon_db_data


def addJobMysql(bot, job_queue):
    chat_id = ''
    logger.info('MySQL job added.')
    try:
        if chat_id not in jobs:
            #job = Job(getMysqlData, 30, repeat=True, context=(chat_id, "Other"))
            job = job_queue.run_repeating(getMysqlData, interval=30, first=5, context=(chat_id, "Other"))
            # Add to jobs
            jobs[chat_id] = job
            #job_queue.put(job)

    except Exception as e:
        logger.error('MySQL job failed.')


def alarm(bot, job):
    chat_id = job.context[0]
    #logger.info('[%s] Checking alarm.' % (chat_id))

    checkAndSend(bot, chat_id, thismodule.pokemon_db_data)


def addJob(bot, update, job_queue):
    chat_id = update.message.chat_id
    userName = update.message.from_user.username
    #logger.info('[%s@%s] Adding job.' % (userName, chat_id))

    try:
        if chat_id not in jobs:
            #job = Job(alarm, 30, repeat=True, context=(chat_id, "Other"))
            job = job_queue.run_repeating(alarm, interval=30, first=0, context=(chat_id, "Other"))
            # Add to jobs
            jobs[chat_id] = job
            #job_queue.put(job)

            # User dependant
            if chat_id not in sent:
                sent[chat_id] = dict()
            if chat_id not in locks:
                locks[chat_id] = threading.Lock()
            text = "Scanner gestartet."
            bot.sendMessage(chat_id, text)
    except Exception as e:
        logger.error('[%s@%s] %s' % (userName, chat_id, repr(e)))


def addJob_silent(bot, chat_id, job_queue):
    userName = ''
    #logger.info('[%s@%s] Adding job.' % (userName, chat_id))

    try:
        if chat_id not in jobs:
            #job = Job(alarm, 30, repeat=True, context=(chat_id, "Other"))
            job = job_queue.run_repeating(alarm, interval=30, first=0, context=(chat_id, "Other"))
            # Add to jobs
            jobs[chat_id] = job
            #job_queue.put(job)

            # User dependant
            if chat_id not in sent:
                sent[chat_id] = dict()
            if chat_id not in locks:
                locks[chat_id] = threading.Lock()

    except Exception as e:
        logger.error('[%s@%s] %s' % (userName, chat_id, repr(e)))


def checkAndSend(bot, chat_id, pokemon_db_data):
    pref = prefs.get(chat_id)
    lock = locks[chat_id]
    message_counter = 0


    try:
        checkAndSetUserDefaults(pref, bot, chat_id)

        mySent = sent[chat_id]
        location_data = pref['location']
        user_send_venue = int(pref['user_send_venue'])

        lock.acquire()

        for pokestops in pokemon_db_data:
            # Get pokestop_id and check if already sent
            pokestop_id = pokestops.getPokestopID()

            if pokestop_id in mySent:
                continue
            # Check if pokestops inside radius
            if not pokestops.filterbylocation(location_data):
                continue

            # Get general Pokémon infos
            pokestop_name = pokestops.getPokestopName()
            latitude = pokestops.getLatitude()
            longitude = pokestops.getLongitude()
            disappear_time = pokestops.getPokestopExpiration()
            delta = disappear_time - datetime.utcnow()
            deltaStr = '%02dm:%02ds' % (int(delta.seconds / 60), int(delta.seconds % 60))
            disappear_time_str = disappear_time.replace(tzinfo=timezone.utc).astimezone(tz=None).strftime("%H:%M:%S")
            grunt_type = pokestops.getGruntType()
            if grunt_type is None:
                grunt_type = 0
            grunt_forms = {0:"Unbekannt", 1:"Blance", 2:"Candela", 3:"Spark", 4:"Zufall", 5:"Zufall", 6:"Käfer", 7:"Käfer", 8:"Geist", 9:"Geist", 10:"Unlicht", 11:"Unlicht", 12:"Drache", 13:"Drache", 14:"Fee", 15:"Fee", 16:"Kampf", 17:"Kampf", 18:"Feuer", 19:"Feuer", 20:"Flug", 21:"Flug", 22:"Pflanze", 23:"Pflanze", 24:"Boden", 25:"Boden", 26:"Eis", 27:"Eis", 28:"Stahl", 29:"Stahl", 30:"Normal", 31:"Normal", 32:"Gift", 33:"Gift", 34:"Psycho", 35:"Psycho", 36:"Gestein", 37:"Gestein", 38:"Wasser", 39:"Wasser", 40:"Giovanni"}

            if user_send_venue == 0:
                pstname = "*%s*" % (pokestop_name)
                address = "*%s* - Bis %s (%s)" % (grunt_forms[int(grunt_type)], disappear_time_str, deltaStr)
            else:
                pstname = "%s" % (pokestop_name)
                address = "%s - Bis %s (%s)" % (grunt_forms[int(grunt_type)], disappear_time_str, deltaStr)
            # Add pokestop_id to mySent after filter
            mySent[pokestop_id] = disappear_time
            notDisappeared = delta.seconds > 0

            if message_counter > 10:
                bot.sendMessage(chat_id, text = 'Es wurden zu viele Pokéstops gefunden. Bitte habe etwas geduld, bis alle versendet wurden. Das passiert normalerweise nur beim ersten start.')
                logger.info('Too many sent')
                break

            if notDisappeared and message_counter <= 10:
                try:
                    if user_send_venue == 0:
                        bot.sendLocation(chat_id, latitude, longitude)
                        bot.sendMessage(chat_id, text = '*%s* %s.'
                            % (pstname, address), parse_mode='Markdown')
                    else:
                        bot.sendVenue(chat_id, latitude, longitude, pstname, address)

                    message_counter += 1

                except Exception as e:
                    logger.error('[%s] %s' % (chat_id, repr(e)))

    except Exception as e:
        logger.error('[%s] %s' % (chat_id, repr(e)))
    lock.release()

    # Clean already disappeared pokemon
    current_time = datetime.utcnow() - dt.timedelta(minutes=10)
    try:

        lock.acquire()
        toDel = []
        for pokestop_id in mySent:
            time = mySent[pokestop_id]
            if time < current_time:
                toDel.append(pokestop_id)
        for pokestop_id in toDel:
            del mySent[pokestop_id]
    except Exception as e:
        logger.error('[%s] %s' % (chat_id, repr(e)))
    lock.release()
    #logger.info('Done.')

def read_config():
    config_path = os.path.join(
        os.path.dirname(sys.argv[0]), "config-bot.json")
    logger.info('Reading config: <%s>' % config_path)
    global config

    try:
        with open(config_path, "r", encoding='utf-8') as f:
            config = json.loads(f.read())
    except Exception as e:
        logger.error('%s' % (repr(e)))
        config = {}
    report_config()

def report_config():

    logger.info('TELEGRAM_TOKEN: <%s>' % (config.get('TELEGRAM_TOKEN', None)))
    logger.info('DB_CONNECT: <%s>' % (config.get('DB_CONNECT', None)))

def read_pokemon_names(loc):
    logger.info('Reading pokemon names. <%s>' % loc)
    config_path = "locales/pokemon." + loc + ".json"

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            pokemon_name[loc] = json.loads(f.read())
    except Exception as e:
        logger.error('%s' % (repr(e)))
        # Pass to ignore if some files missing.
        pass

def read_move_names(loc):
    logger.info('Reading move names. <%s>' % loc)
    config_path = "locales/moves." + loc + ".json"

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            move_name[loc] = json.loads(f.read())
    except Exception as e:
        logger.error('%s' % (repr(e)))
        # Pass to ignore if some files missing.
        pass


def ReadIncomingCommand(bot, update, args, job_queue):
    Authenticated = 0

    ChatId = update.message.chat_id
    IncomingCommand = update.message.text.upper().split()[0]
    ChatType = update.message.chat.type
    UserID = update.effective_user.id

    if ChatType == 'private':
        Authenticated = 1
    else:
        GroupAdmins = bot.get_chat_administrators(chat_id = ChatId)
        for Admin in GroupAdmins:
            if Admin.user.id == UserID:
                Authenticated = 1
                break

    if Authenticated == 0:
        return

    # Commands
    # Without args:
    if IncomingCommand in ['/START']:
        cmd_start(bot, update, job_queue)
    elif IncomingCommand in ['/STATUS']:
        cmd_status(bot, update)
    elif IncomingCommand in ['/NACHRICHT', '/MESSAGE']:
        cmd_SwitchVenue(bot, update)
    elif IncomingCommand in ['/HILFE', '/HELP']:
        cmd_help(bot, update)
    elif IncomingCommand in ['/SPEICHERN', '/SAVE']:
        cmd_save(bot, update)
    elif IncomingCommand in ['/ENDE', '/CLEAR']:
        cmd_clear(bot, update)

    # With args:
    elif IncomingCommand in ['/RADIUS']:
        cmd_radius(bot, update, args)

    # With job_queue
    elif IncomingCommand in ['/LADEN', '/LOAD']:
        cmd_load(bot, update, job_queue)
    elif IncomingCommand in ['/STANDORT', '/LOCATION']:
        cmd_location_str(bot, update, args, job_queue)

    else:
        cmd_unknown(bot, update)

def main():
    logger.info('Starting...')
    read_config()

    global dataSource
    dataSource = None

    dataSource = DataSources.DSPokemonGoMapIVMysql(config.get('DB_CONNECT', None))

    if not dataSource:
        raise Exception("Error in MySQL connection")


    #ask it to the bot father in telegram
    token = config.get('TELEGRAM_TOKEN', None)
    updater = Updater(token)
    b = Bot(token)
    logger.info("BotName: <%s>" % (b.name))

    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    AvailableCommands = [
        'Nachricht',
        'Start',
        'Status',
        'Help','Hilfe',
        'Ende','Clear',
        'Speichern','Save',
        'Laden','Load',
        'Radius',
        'Standort','Location']

    dp.add_handler(CommandHandler(AvailableCommands, ReadIncomingCommand, pass_args = True, pass_job_queue=True))
    dp.add_handler(MessageHandler(Filters.location, cmd_location))
    dp.add_handler(MessageHandler((Filters.text | Filters.command), cmd_unknown))

    # log all errors
    dp.add_error_handler(error)

    # add the configuration to the preferences
    prefs.add_config(config)

    # Start the Bot
    bot = b;
    updater.start_polling()
    j = updater.job_queue
    addJobMysql(b,j)
    thismodule.pokemon_db_data = getMysqlData(b,j)

    # Check if directory exists
    if not os.path.exists("userdata/"):
        os.makedirs("userdata/")

    else:
        allids = os.listdir("userdata/")
        newids = []

        for x in allids:
            newids = x.replace(".json", "")
            chat_id = int(newids)
            j = updater.job_queue
            #logger.info('%s' % (chat_id))

            try:
                cmd_load_silent(b, chat_id, j)
            except Exception as e:
                logger.error('%s' % (chat_id))
                logger.info("FEHLER!!!!")

    logger.info('Started!')

    # Block until the you presses Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == '__main__':
    main()
