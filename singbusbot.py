import json
import requests
import pickle
import os
import logging

import telegram
import psycopg2

import updateBusData
import telegramCommands
from one_map_utils import *
from telegram import *
from telegram.ext import *
from telegram.error import TimedOut
from urllib import parse
from scipy import spatial
from datetime import datetime, timedelta, time

TOKEN = os.getenv("TOKEN")
LTA_ACCOUNT_KEY = os.getenv("LTA_Account_Key")
OWNER_ID = os.getenv("owner_id")
BOT_URL = "https://api.telegram.org/bot{}/".format(TOKEN)

# Sets the database credentials based on testing vs prod environment
if os.environ.get("DATABASE_URL"):
    parse.uses_netloc.append("postgres")
    db_url = parse.urlparse(os.environ["DATABASE_URL"])
    DATABASE_CREDENTIALS = f"""dbname='{db_url.path[1:]}'
                               user='{db_url.username}'
                               password='{db_url.password}'
                               host='{db_url.hostname}'
                               port='{db_url.port}'"""
else:
    DATABASE_CREDENTIALS = """dbname='user_data'
       user='postgres'
       password='password'
       host='127.0.0.1'
       port='5432'"""

updater = Updater(token=TOKEN, use_context=True)
job = updater.job_queue
dispatcher = updater.dispatcher
conn = psycopg2.connect(DATABASE_CREDENTIALS)


####################
# HELPER FUNCTIONS #
####################


# Adds a Filter to filter out the telegram TimedOut Errors
class TimedOutFilter(logging.Filter):
    def filter(self, record):
        if "Error while getting Updates: Timed out" in record.getMessage():
            return False
        else:
            return True


class APSchedulerFilter(logging.Filter):
    def filter(self, record):
        if "_trigger_timeout" in record.getMessage():
            return False
        elif "bot_send_typing" in record.getMessage():
            return False
        elif "Removed job" in record.getMessage():
            return False
        else:
            return True


def _escape_markdown(message):
    markdownv2_escape = {
        "-": "\-",
        ".": "\.",
        "(": "\(",
        ")": "\)",
    }
    return message.translate(str.maketrans(markdownv2_escape))


def check_bus_data(_):
    """
    Checks if the bus data on disk is updated if not, informs the owner
    """
    if all(updateBusData.check_bus_data()):
        logging.info("Bus data is up to date")
    else:
        logging.warning("Bus data needs to be updated")
        send_message_to_owner(updater.bot, "WARNING: Bus data out of date")


def broadcast_message(bot, text):
    global conn
    if conn.closed:
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
    cur = conn.cursor()

    cur.execute('''SELECT * FROM user_data WHERE state = 1''')
    row = cur.fetchall()
    for x in row:
        chat_id = json.loads(x[0])
        try:  # Try to send a message to the user. If the user has blocked the bot, just skip
            bot.send_message(chat_id=chat_id, text=text, parse_mode="MarkdownV2")
        except telegram.error.Unauthorized:
            pass
    cur.close()
    logging.info("Broadcast complete")


def send_message_to_owner(bot, message):
    bot.send_message(chat_id=OWNER_ID, text=message)


def fetch_user_favourites(user_id):
    """
    Returns a list of the user's favourite bus stops

    :param user_id: Telegram User ID
    :return: List of favourite bus stops: [[Code, Saved Name],[]]
    """
    global conn
    if conn.closed:
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
    cur = conn.cursor()
    cur.execute('''SELECT * FROM user_data WHERE '%s' = user_id''', (user_id,))
    row = cur.fetchall()

    if row:
        favourites = json.loads(row[0][3])
    else:
        favourites = []

    cur.close()
    return favourites


def generate_reply_keyboard(favourites):
    """
    Creates a Telegram Keyboard with favourite bus stops

    :param favourites: List of favourite bus stops
    :return: List of KeyboardButtons for ReplyKeyboard
    """

    temp = []
    reply_keyboard = []

    for i, favourite in enumerate(favourites, start=1):
        temp.append(favourite[0])
        if i % 2 == 0:
            reply_keyboard.append(temp)
            temp = []
        if i % 2 == 1 and i == len(favourites):
            reply_keyboard.append(temp)

    reply_keyboard.append([telegram.KeyboardButton(text="Bus Stops Near Me", request_location=True)])
    return reply_keyboard


##################
# MAIN FUNCTIONS #
##################


def commands(update, context):
    global conn
    if conn.closed:
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
    cur = conn.cursor()
    message = update.message.text
    user = update.effective_user
    reply_text = telegramCommands.check_commands(context.bot, message)

    if '/broadcast' in message and user.id == int(OWNER_ID):
        broadcast_message(context.bot, reply_text)
    elif message == '/start':
        # Adds a new row of data for new users
        cur.execute(
            '''INSERT INTO user_data (user_id, username, first_name, favourite, state) VALUES ('%s', %s, %s, %s, 1)
            ON CONFLICT (user_id) DO UPDATE SET state = 1''',
            (user.id, user.username, user.first_name, '[]'))
        conn.commit()
    elif '/stop' in message:
        cur.execute('''UPDATE user_data SET state = 0 WHERE user_id = '%s' ''', (user.id,))
        conn.commit()
    elif not reply_text:
        logging.info(f"Invalid Command: {user.first_name} [{user.username}] ({user.id}), {message}")
        update.message.reply_text(text="Please enter a valid command")

    favourites = fetch_user_favourites(user.id)
    reply_keyboard = generate_reply_keyboard(favourites)
    cur.close()
    # Logs and sends message
    logging.info(f"Command: {user.first_name} [{user.username}] ({user.id}), {message}")
    reply_text = _escape_markdown(reply_text)
    update.message.reply_markdown_v2(text=reply_text,
                                     reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))


def check_valid_favourite(message):
    """
    Checks if the passed bus stop is a favourite bus stop

    :param message: update.message object
    :return: Favourite bus stop code if exists, else original message
    """

    global conn
    if conn.closed:
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
    cur = conn.cursor()
    cur.execute('''SELECT * FROM user_data WHERE '%s' = user_id''', (message.from_user.id,))
    text = message.text
    row = cur.fetchall()

    if row:
        favourites = json.loads(row[0][3])
    else:
        return text

    for favourite in favourites:
        # favourite = [saved name, bus stop id]
        if text in favourite[0]:
            return favourite[1]

    cur.close()
    return text


def check_valid_bus_stop(message):
    """
    Takes in a whole message and determine if it's a valid bus stop

    :param message: str of sent message
    :return: bus stop code, bus stop name
    """

    if not message:     # If message is NoneType
        return False, False

    # Converts message to a processable form
    message = "".join([x.lower() for x in message if x.isalnum()])
    # Loads bus stop database from busStop.txt
    with open("busStop.txt", "rb") as afile:
        bus_stop_db = pickle.load(afile)

    # For each bus stop in the database, check if passed message is found
    # TODO: See if there's a way to speed this checking up. A dict?
    for sublist in bus_stop_db[0]:
        bus_stop_name = "".join([y.lower() for y in sublist[1] if y.isalnum()])
        # Check for bus stop number or stop name
        if (message in sublist) or (message == bus_stop_name):
            # Return bus stop code, bus stop name
            return sublist[0], sublist[1]

    return False, False


def get_next_bus_time(service):
    """
    Processes the API call for the next 2 bus timings.

    :param service: LTA_API JSON given a bus stop
    :return: time_left, time_following_left
    """

    # Pass pjson data to return timeLeft and timeFollowingLeft
    if service["NextBus"]["EstimatedArrival"].split("+")[0] == "":
        # If next bus timing does not exist, return NA
        return "NA", "NA"

    current_time = (datetime.utcnow() + timedelta(hours=8)).replace(microsecond=0)

    # Get next bus timing
    next_bus_time = datetime.strptime(service["NextBus"]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S")
    if current_time > next_bus_time:  # If bus is late
        time_left = "00"
    else:
        time_left = str((next_bus_time - current_time)).split(":")[1]  # Return time next for next bus

    # Get following bus timing
    try:
        following_bus_time = datetime.strptime(service["NextBus2"]["EstimatedArrival"].split("+")[0],
                                               "%Y-%m-%dT%H:%M:%S")
        time_following_left = str(following_bus_time - current_time).split(":")[1]
        return time_left, time_following_left
    except ValueError:
        return time_left, "NA"


def create_bus_timing_message(bus_stop_code, bus_stop_name):
    """
    Creates the bus timing message and formats it

    :param bus_stop_code: str, 5-digit bus stop code
    :param bus_stop_name: str, name of bus stop
    :return: str, message to be sent
    """

    text = f"*{bus_stop_code} - {bus_stop_name}*\n"

    # HTTP Request to check bus timings
    url = f"http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2?BusStopCode={bus_stop_code}"
    headers = {"AccountKey": LTA_ACCOUNT_KEY}
    r = requests.get(url, headers=headers)
    pjson = r.json()

    # For each bus service that is returned
    for service in pjson["Services"]:
        time_left, time_following_left = get_next_bus_time(service)

        # Display time left for each service
        text += str(service['ServiceNo']).ljust(7)
        if time_left == "00":
            text += "Arr".ljust(6)
        else:
            text += f"{time_left} min".ljust(6)

        text += "    "

        if time_following_left == "00":
            text += "Arr".ljust(6)
        else:
            text += f"{time_following_left} min"
        text += "\n"

    if not pjson["Services"]:  # If no results were returned
        text += "No more buses at this hour"

    return text


def send_bus_timings(update, _):
    # Assign message variable depending on request type
    if update.callback_query:
        if update.callback_query.data == 'Refresh':
            message = update.effective_message.text.split()[0]
        elif update.callback_query.data:    # Elif the callback_query is a bus stop code
            message = update.callback_query.data
        else:
            message = ""
    else:  # Check if it exists in user's favourites
        message = check_valid_favourite(update.message)

    user = update.effective_user

    # Call function and assign to variables
    bus_stop_code, bus_stop_name = check_valid_bus_stop(message)
    favourites = fetch_user_favourites(user.id)
    reply_keyboard = generate_reply_keyboard(favourites)

    if not bus_stop_code:
        return search_text(_, _, update)

    else:
        text = create_bus_timing_message(bus_stop_code, bus_stop_name)
        text = _escape_markdown(text)

    # Format of inline refresh button
    button_list = [
        [InlineKeyboardButton("Refresh", callback_data="Refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(button_list)

    # If it's a callback function for refreshing,
    if update.callback_query and update.callback_query.data == 'Refresh':
        # Reply to the user and log it
        text += f"\n_Last Refreshed: {(datetime.utcnow() + timedelta(hours=8)).strftime('%H:%M:%S')}_"
        logging.info(f"Refresh: {user.first_name} [{user.username}] ({user.id}), {message}")
        update.effective_message.edit_text(text=text, parse_mode="MarkdownV2", reply_markup=reply_markup)
        update.callback_query.answer()

    # Else, send a new message
    else:
        logging.info(f"Request: {user.first_name} [{user.username}] ({user.id}), {message}")
        update.effective_message.reply_markdown_v2(text=text, reply_markup=reply_markup)

        if update.callback_query:
            update.callback_query.answer()


def search_location(update):
    user = update.message.from_user
    location = (update.message.location.latitude, update.message.location.longitude)

    with open("busStop.txt", "rb") as afile:
        bus_stop_db = pickle.load(afile)

    text = ""
    tree = spatial.KDTree(bus_stop_db[1])
    index = tree.query(location, k=5)
    for x in range(len(index[1])):
        bus_stop_code = bus_stop_db[0][index[1][x]][0]
        bus_stop_name = bus_stop_db[0][index[1][x]][1]

        text += create_bus_timing_message(bus_stop_code, bus_stop_name)
        text += "\n"

    text = _escape_markdown(text)
    logging.info(f"Location: {user.first_name} [{user.username}] ({user.id}), {location}")
    update.message.reply_markdown_v2(text=text)


def search_text(update, _, original_update=None):
    if not original_update:
        update.callback_query.answer()
        _, query, user_page_num = update.callback_query.data.split(":::")
        user_page_num = int(user_page_num)
    else:
        query = original_update.effective_message.text
        user = original_update.effective_message.from_user
        user_page_num = 1
        logging.info(f"Search: {user.first_name} [{user.username}] ({user.id}), {query}")

    def _generate_pagination(query):
        search_page_num, results_total = 1, 0
        all_pages, current_page = [], []
        places_list = set()

        results = search_one_map(query, search_page_num)
        total_num_pages, num_found = results['totalNumPages'], results['found']

        while True:
            if not results['results']:
                # Return any possible results if they have been added
                if results_total:
                    return all_pages, results_total
                # If not, there are no results for the query
                return None, 0

            for place in results['results']:
                if place['SEARCHVAL'] not in places_list:
                    places_list.add(place['SEARCHVAL'])
                    callback_data = str((float(place['LATITUDE']), float(place['LONGITUDE'])))
                    current_page.append([InlineKeyboardButton(place['SEARCHVAL'], callback_data=callback_data)])

                    # Ensure that only a maximum of 30 results can be found
                    results_total += 1
                    if results_total > 30:
                        return False, num_found

                # Creates a new page every 10 results
                if len(current_page) == 10:
                    all_pages.append(current_page)
                    current_page = []

            # Returns once all results have been added
            search_page_num += 1
            if search_page_num > total_num_pages:
                all_pages.append(current_page)
                return all_pages, results_total

            results = search_one_map(query, search_page_num)

    pagination, num_found = _generate_pagination(query)
    reply_keyboard = None

    if pagination is False:
        text = f"🔍: {query}\n{num_found} results found.\nToo many results... Please try again"
    elif pagination is None:
        text = f"🔍: {query}\nNo results found... Please try again"
    else:
        # Selects the correct page for reply keyboard, based on the user_page_num
        reply_keyboard = pagination[user_page_num - 1]

        # Adds navigation buttons based on total number of pages in pagination
        if len(pagination) != 1:
            if user_page_num == 1:
                reply_keyboard.append([InlineKeyboardButton(">", callback_data=f">:::{query}:::2")])
            elif user_page_num == min(len(pagination), 3):
                reply_keyboard.append([InlineKeyboardButton("<", callback_data=f"<:::{query}:::{user_page_num-1}")])
            else:
                reply_keyboard.append([InlineKeyboardButton("<", callback_data=f"<:::{query}:::{user_page_num-1}"),
                                       InlineKeyboardButton(">", callback_data=f">:::{query}:::{user_page_num+1}")])

        text = f"🔍: {query}\n{num_found} results found.\n\nPage: {user_page_num}/{len(pagination)}"
        reply_keyboard = InlineKeyboardMarkup(reply_keyboard)

    text = _escape_markdown(text)

    if not original_update:
        update.effective_message.edit_text(text, reply_markup=reply_keyboard, parse_mode='MarkdownV2')
    else:
        original_update.effective_message.reply_markdown_v2(text, reply_markup=reply_keyboard)


#####################
# BUS ROUTE HANDLER #
#####################

# Create a new telegram filter, filter out bus Services
class FilterBusService(MessageFilter):
    def filter(self, message):
        if not message.text:    # Handles non-message entities to prevent errors
            return False
        with open("busServiceNo.txt", "rb") as afile:
            bus_service_no = pickle.load(afile)
        return message.text.upper() in bus_service_no


bus_service_filter = FilterBusService()


def ask_bus_route(update, _):
    # Takes in bus service and outputs direction, waiting for user's confirmation
    bus_number = update.message.text.upper()
    user = update.message.from_user

    with open("busService.txt", "rb") as afile:
        bus_service_db = pickle.load(afile)

    # Find the direction(s) out that bus service
    directions = [element for element in bus_service_db if element['service_no'] == bus_number]
    reply_keyboard = []

    # Generates a reply_keyboard with the directions
    for i, direction in enumerate(directions):
        bus_stop_code_start, bus_stop_name_start = check_valid_bus_stop(direction["bus_stops"][0])
        bus_stop_code_end, bus_stop_name_end = check_valid_bus_stop(direction["bus_stops"][-1])
        reply_keyboard.append([InlineKeyboardButton(f"{bus_stop_name_start} - {bus_stop_name_end}",
                                                    callback_data=f"BUS ROUTE:::{bus_number}:::{i}")])

    update.message.reply_text(f"🚌 Bus {bus_number}\nWhich direction?", reply_markup=InlineKeyboardMarkup(reply_keyboard))
    logging.info(f"Service Request: {user.first_name} [{user.username}] ({user.id}), {bus_number}")


def bot_send_typing(context):
    context.bot.send_chat_action(chat_id=context.job.context, action="typing", timeout=30)


def send_bus_route(update, context):  # Once user has replied with direction, output the arrival timings
    update.callback_query.answer()
    user = update.effective_user
    job_send_typing = job.run_repeating(bot_send_typing, interval=5, first=0, context=update.effective_chat.id)

    # Create the usual reply_keyboard
    favourites = fetch_user_favourites(user.id)
    reply_keyboard = generate_reply_keyboard(favourites)

    with open("busService.txt", "rb") as afile:
        bus_service_db = pickle.load(afile)

    _, bus_number, direction = update.callback_query.data.split(":::")
    directions = [element for element in bus_service_db if element['service_no'] == bus_number]
    _, bus_stop_name_start = check_valid_bus_stop(directions[int(direction)]["bus_stops"][0])
    _, bus_stop_name_end = check_valid_bus_stop(directions[int(direction)]["bus_stops"][-1])

    header = f"Bus {str(bus_number)} ({bus_stop_name_start} - {bus_stop_name_end})"
    message = f"__{header}__\n"
    flag = 0

    for bus_stop_code in directions[int(direction)]["bus_stops"]:  # For every bus stop code in that direction
        url = f"http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2?BusStopCode={bus_stop_code}"
        headers = {"AccountKey": LTA_ACCOUNT_KEY}
        r = requests.get(url, headers=headers)
        pjson = r.json()

        # Select the correct bus service from raw data
        service = [element for element in pjson["Services"] if element['ServiceNo'] == bus_number]
        if service:     # Get the arrival time
            time_left, time_following_left = get_next_bus_time(service[0])
        else:       # If there are no more buses for the day
            time_left = "NA"

        bus_stop_code, bus_stop_name = check_valid_bus_stop(bus_stop_code)
        text = f"*{bus_stop_name}* ( /{bus_stop_code} )   "
        if time_left != "NA":
            flag = 1
        if time_left == "00":
            text += "Arr"
        else:
            text += f"{time_left} min"
        message += text + "\n"

    if flag == 0:
        message = f"__{header}__\nNo more buses at this hour"

    job_send_typing.schedule_removal()
    message = _escape_markdown(message)
    update.callback_query.message.reply_markdown_v2(message, reply_markup=ReplyKeyboardMarkup(reply_keyboard),
                                                    api_kwargs={'resize_keyboard': True})

    logging.info(f"Service Request: {user.first_name} [{user.username}] ({user.username}), {header}")
    context.user_data.clear()
    return ConversationHandler.END


###############
# ONE MAP API #
###############


def search_location_or_postal(update, _):
    user = update.effective_user

    if update.callback_query:
        update.callback_query.answer()
        text = eval(update.callback_query.data)
        lat, long = text
    elif update.effective_message.location:
        lat = update.message.location.latitude
        long = update.message.location.longitude
        text = (lat, long)
    else:   # If it's a postal code search
        pjson = search_one_map(update.effective_message.text)
        if pjson['found'] == 0:
            update.message.reply_text("Invalid postal code. Please try again")
            logging.info(f"Invalid postal code: {user.first_name} [{user.username}] ({user.username}), "
                         f"{update.effective_message.text}")
            return
        else:
            lat = float(pjson['results'][0]['LATITUDE'])
            long = float(pjson['results'][0]['LONGITUDE'])
            text = update.effective_message.text

    location = (lat, long)

    with open("busStop.txt", "rb") as afile:
        bus_stop_db = pickle.load(afile)

    tree = spatial.KDTree(bus_stop_db[1])
    index = tree.query(location, k=5)
    points_to_draw = [f'[{lat}, {long}, "255,0,0"]']

    buttons = []

    for x in range(len(index[1])):
        bus_stop_code = bus_stop_db[0][index[1][x]][0]
        bus_stop_name = bus_stop_db[0][index[1][x]][1]
        bus_stop_lat = bus_stop_db[1][index[1][x]][0]
        bus_stop_long = bus_stop_db[1][index[1][x]][1]

        # chr converts the index to capital letters
        points_to_draw.append(f'[{bus_stop_lat}, {bus_stop_long}, "255,255,255", "{chr(x+65)}"]')
        buttons.append([InlineKeyboardButton(text=f'{chr(x+65)}: {bus_stop_code} - {bus_stop_name}',
                                             callback_data=bus_stop_code)])

    points = "|".join(points_to_draw)
    photo = get_one_map_map(lat, long, points)

    logging.info(f"Location: {user.first_name} [{user.username}] ({user.id}), {text}")
    update.effective_message.reply_photo(photo, parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(buttons))


####################
# SETTINGS HANDLER #
####################


# Initialise some variables for the service ConversationHandler function
SETTINGS, RE_SETTINGS, CANCEL, ADD_FAVOURITE, ADD_FAVOURITE_CODE, ADD_FAVOURITE_NAME, \
    CONFIRM_ADD_FAVOURITE, REMOVE_FAVOURITE, CHECK_REMOVE_FAVOURITE, CONFIRM_REMOVE_FAVOURITE = map(chr, range(2, 12))


def settings(update, _):
    if update.callback_query:
        update.callback_query.message.delete()

    user = update.effective_user
    logging.info(f"Accessing settings: {user.first_name} [{user.username}] ({user.id})")
    favourites = fetch_user_favourites(user.id)

    # If user has no favourites, no remove option will be given
    if favourites:
        buttons = [[
            InlineKeyboardButton(text='Add Favourite', callback_data=str(ADD_FAVOURITE)),
            InlineKeyboardButton(text='Remove Favourite', callback_data=str(REMOVE_FAVOURITE))
        ], [
            InlineKeyboardButton(text='Cancel', callback_data=str(CANCEL))
        ]]
    else:
        buttons = [[
            InlineKeyboardButton(text='Add Favourite', callback_data=str(ADD_FAVOURITE))
        ], [
            InlineKeyboardButton(text='Cancel', callback_data=str(CANCEL))
        ]]

    update.effective_message.reply_text("What would you like to do?", reply_markup=InlineKeyboardMarkup(buttons))
    return SETTINGS


def add_favourite(update, context):
    context.user_data.clear()
    buttons = [[InlineKeyboardButton(text='Back', callback_data=str(SETTINGS))]]

    if update.callback_query:
        update.callback_query.answer()
        update.callback_query.message.reply_text("Please enter a bus stop code", reply_markup=InlineKeyboardMarkup(buttons))
        update.callback_query.message.delete()
    else:
        update.message.reply_text("Please enter a bus stop code", reply_markup=InlineKeyboardMarkup(buttons))

    return ADD_FAVOURITE_CODE


def choose_favourite_stop(update, context):
    message = update.message.text

    bus_stop_code, bus_stop_name = check_valid_bus_stop(message)
    buttons = [[InlineKeyboardButton(text='Back', callback_data=str(ADD_FAVOURITE))]]

    if bus_stop_code is False:
        # Informs the user that busStopCode was invalid & logs it
        update.message.reply_text("Try again. Please enter a valid bus stop code", reply_markup=InlineKeyboardMarkup(buttons))
        return ADD_FAVOURITE_CODE

    else:
        favourites = fetch_user_favourites(update.effective_user.id)
        if favourites:
            existing_favourite_codes = list(zip(*favourites))[1]    # Takes all the 1st elements of favourites
            if bus_stop_code in existing_favourite_codes:
                update.message.reply_text("Favourite bus stop already added. Please choose another one",
                                          reply_markup=InlineKeyboardMarkup(buttons))
                return ADD_FAVOURITE_CODE

        context.user_data["bus_stop_code"] = bus_stop_code
        update.message.reply_text(f"What would you like to name: {bus_stop_code} - {bus_stop_name}?",
                                  reply_markup=InlineKeyboardMarkup(buttons))

        return ADD_FAVOURITE_NAME


# Asks user to confirm favourite
def choose_favourite_name(update, context):
    favourites = fetch_user_favourites(update.effective_user.id)

    if favourites:
        existing_favourite_names = list(zip(*favourites))[0]  # Takes all the 0th elements of favourites
        if update.message.text in existing_favourite_names:
            update.message.reply_text("Name already exists. Please choose another name.")
            return ADD_FAVOURITE_NAME

    context.user_data["bus_stop_name"] = update.message.text

    buttons = [[InlineKeyboardButton(text='Yes', callback_data='ADD_YES'),
               InlineKeyboardButton(text='No', callback_data='ADD_NO')]]

    reply_message = f"Please confirm that you would like to add " \
                    f"{context.user_data['bus_stop_name']} - {context.user_data['bus_stop_code']}"
    context.user_data["previous_message"] = reply_message

    update.message.reply_text(reply_message, reply_markup=InlineKeyboardMarkup(buttons))
    return CONFIRM_ADD_FAVOURITE


# Adds favourite into database
def confirm_add_favourite(update, context):
    user = update.effective_user
    favourites = fetch_user_favourites(user.id)
    context.user_data["favourites"] = favourites

    # Adds new favourite to the list
    favourites.append([context.user_data["bus_stop_name"], context.user_data["bus_stop_code"]])
    insert_sf = json.dumps(favourites)
    global conn
    if conn.closed:
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
    cur = conn.cursor()
    cur.execute(
        '''INSERT INTO user_data (user_id, username, first_name, favourite, state) VALUES ('%s', %s, %s, %s, 1)
        ON CONFLICT (user_id) DO UPDATE SET favourite = %s; ''',
        (user.id, user.username, user.first_name, insert_sf, insert_sf))
    cur.close()
    conn.commit()

    reply_keyboard = generate_reply_keyboard(favourites)
    update.effective_message.edit_text(context.user_data["previous_message"])
    update.effective_message.reply_text("Added favourite bus stop!",
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    logging.info("Added New Favourite: %s [%s] (%s)", user.first_name, user.username, user.id)
    context.user_data.clear()

    buttons = [[
        InlineKeyboardButton(text='Add Favourite', callback_data=str(ADD_FAVOURITE)),
        InlineKeyboardButton(text='Remove Favourite', callback_data=str(REMOVE_FAVOURITE))
    ], [
        InlineKeyboardButton(text='Cancel', callback_data=str(CANCEL))
    ]]
    update.effective_message.reply_text("Is there anything else you would like to do?",
                                        reply_markup=InlineKeyboardMarkup(buttons))

    return SETTINGS


def remove_favourite(update, context):
    update.callback_query.answer()
    context.user_data.clear()

    # Gets data from database
    favourites = fetch_user_favourites(update.effective_user.id)
    context.user_data["favourites"] = favourites
    reply_keyboard = generate_reply_keyboard(favourites)
    reply_keyboard.pop()    # Removes the location request from the keyboard
    reply_keyboard.append([KeyboardButton(text='Back', callback_data=str(SETTINGS))])

    update.callback_query.message.reply_text("What bus stop would you like to remove?",
                                             reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    update.callback_query.message.delete()
    return CHECK_REMOVE_FAVOURITE


# Asks user to confirm removing bus stop
def check_remove_favourite(update, context):
    favourites = context.user_data["favourites"]
    for favourite in favourites:
        if update.message.text == favourite[0]:
            stop_to_remove = favourite
            break
    else:
        reply_keyboard = generate_reply_keyboard(favourites)
        reply_keyboard.append([InlineKeyboardButton(text='Cancel', callback_data=str(CANCEL))])
        update.message.reply_text("Please choose a valid favourite bus stop!",
                                  reply_markup=ReplyKeyboardMarkup(reply_keyboard))
        return REMOVE_FAVOURITE

    context.user_data["remove"] = stop_to_remove

    buttons = [[InlineKeyboardButton(text='Yes', callback_data='REMOVE_YES'),
                InlineKeyboardButton(text='No', callback_data='REMOVE_NO')]]
    reply_message = f"Are you sure you want to remove {stop_to_remove[0]} - {stop_to_remove[1]}?"
    context.user_data["previous_message"] = reply_message

    update.message.reply_text(reply_message, reply_markup=InlineKeyboardMarkup(buttons))

    return CONFIRM_REMOVE_FAVOURITE


def confirm_remove_favourite(update, context):
    user = update.effective_user

    # Inserts the new list into the database
    context.user_data["favourites"].remove(context.user_data["remove"])
    favourites = context.user_data["favourites"]
    insert_sf = json.dumps(favourites)
    global conn
    if conn.closed:
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
    cur = conn.cursor()
    cur.execute('''UPDATE user_data SET favourite = %s WHERE user_id = '%s' ''',
                (insert_sf, user.id))
    cur.close()
    conn.commit()

    reply_keyboard = generate_reply_keyboard(favourites)

    logging.info("Removed favourite: %s [%s] (%s)", user.first_name, user.username, user.id)
    update.effective_message.edit_text(context.user_data["previous_message"])
    update.effective_message.reply_text("Removed favourite bus stop!",
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))

    context.user_data.clear()

    # If user has no favourites, no remove option will be given
    if favourites:
        buttons = [[
            InlineKeyboardButton(text='Add Favourite', callback_data=str(ADD_FAVOURITE)),
            InlineKeyboardButton(text='Remove Favourite', callback_data=str(REMOVE_FAVOURITE))
        ], [
            InlineKeyboardButton(text='Cancel', callback_data=str(CANCEL))
        ]]
    else:
        buttons = [[
            InlineKeyboardButton(text='Add Favourite', callback_data=str(ADD_FAVOURITE))
        ], [
            InlineKeyboardButton(text='Cancel', callback_data=str(CANCEL))
        ]]

    update.effective_message.reply_text("Is there anything else you would like to do?",
                                        reply_markup=InlineKeyboardMarkup(buttons))

    return SETTINGS


#########################################
# CONVERSATION HANDLER HELPER FUNCTIONS #
#########################################


# Allows user to quit at anytime
def cancel(update, context):
    # Generates reply_keyboard
    favourites = fetch_user_favourites(update.effective_user.id)
    reply_keyboard = generate_reply_keyboard(favourites)

    if update.effective_message.reply_markup:   # Removes any inline keyboard if applicable
        update.effective_message.edit_text(update.effective_message.text)

    update.effective_message.reply_text("Cancelled",
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    if update.callback_query:
        update.callback_query.answer()
    context.user_data.clear()

    return ConversationHandler.END


def timeout(update, context):
    favourites = fetch_user_favourites(update.effective_user.id)
    reply_keyboard = generate_reply_keyboard(favourites)
    context.user_data.clear()

    update.effective_message.reply_text("Operated timed out. Please try again",
                                        reply_markup=ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True))
    return ConversationHandler.TIMEOUT


def waiting(update, _):
    update.message.reply_text(text="Still processing the last request... Please wait a while.")
    return ConversationHandler.WAITING


def unknown(update, _):
    update.message.reply_text(text="Please enter a valid command")
    logging.info("Invalid command: %s [%s] (%s)", update.message.from_user.first_name,
                 update.message.from_user.username, update.message.from_user.id)


def error_callback(update, context):
    if context.error == TimedOut:
        return
    elif context.error == "connection already closed":
        # If the connection to the database gets closed, reconnect
        global conn
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
        return
    else:
        logging.warning(f'Update "{update}" caused error "{context.error}"')
        raise context.error


def main():
    # Create users table for initial setup
    global conn
    if conn.closed:
        conn = psycopg2.connect(DATABASE_CREDENTIALS)
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS user_data(user_id TEXT, username TEXT, first_name TEXT, favourite TEXT, state int, "
        "PRIMARY KEY (user_id));")
    conn.commit()
    cur.close()

    # Logging configurations
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    telegram_logger = logging.getLogger('telegram.ext.updater')
    telegram_logger.addFilter(TimedOutFilter())
    apscheduler_logger = logging.getLogger('apscheduler.scheduler')
    apscheduler_logger.addFilter(APSchedulerFilter())
    apexecuter_logger = logging.getLogger('apscheduler.executors.default')
    apexecuter_logger.addFilter(APSchedulerFilter())

    command_handler = CommandHandler(['start', 'help', 'about', 'feedback', 'broadcast', 'stop'], commands)
    refresh_handler = CallbackQueryHandler(send_bus_timings, pattern='Refresh')
    search_location_or_postal_handler = MessageHandler(Filters.regex('\d{6}') | Filters.location,
                                                       search_location_or_postal)
    search_text_location_handler = CallbackQueryHandler(search_location_or_postal, pattern='\(\d+\.\d+, \d+\.\d+\)')
    search_text_page_handler = CallbackQueryHandler(search_text, pattern='[<>]')
    bus_handler = MessageHandler(Filters.text, send_bus_timings)
    bus_postal_handler = CallbackQueryHandler(send_bus_timings, pattern='\d{5}')
    bus_service_handler = MessageHandler(bus_service_filter, ask_bus_route)
    bus_route_handler = CallbackQueryHandler(send_bus_route, pattern="BUS ROUTE")
    unknown_handler = MessageHandler(Filters.all, unknown)

    add_favourite_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_favourite, pattern=f'{str(ADD_FAVOURITE)}')],

        states={
            ADD_FAVOURITE_CODE: [MessageHandler(Filters.text & (~Filters.command), choose_favourite_stop)],
            ADD_FAVOURITE_NAME: [MessageHandler(Filters.text & (~Filters.command), choose_favourite_name)],
            CONFIRM_ADD_FAVOURITE: [CallbackQueryHandler(confirm_add_favourite, pattern="ADD_YES"),
                                    CallbackQueryHandler(add_favourite, pattern="ADD_NO")]
        },

        fallbacks=[CommandHandler('cancel', cancel),
                   CallbackQueryHandler(cancel, pattern=f"{str(CANCEL)}"),
                   CallbackQueryHandler(settings, pattern=f"{str(SETTINGS)}"),
                   CallbackQueryHandler(add_favourite, pattern=f"{str(ADD_FAVOURITE)}")],

        map_to_parent={
            SETTINGS: SETTINGS,
            ConversationHandler.TIMEOUT: ConversationHandler.TIMEOUT,
            ConversationHandler.END: ConversationHandler.END
        },
        conversation_timeout=30
    )

    remove_favourite_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_favourite, pattern=f'{str(REMOVE_FAVOURITE)}')],

        states={
            CHECK_REMOVE_FAVOURITE: [MessageHandler(Filters.text & ~Filters.command & ~Filters.regex('Back'),
                                                    check_remove_favourite)],
            CONFIRM_REMOVE_FAVOURITE: [CallbackQueryHandler(confirm_remove_favourite, pattern="REMOVE_YES"),
                                       CallbackQueryHandler(remove_favourite, pattern="REMOVE_NO")]
        },

        fallbacks=[CommandHandler('cancel', cancel),
                   MessageHandler(Filters.regex('Back'), settings),
                   CallbackQueryHandler(cancel, pattern=f"{str(CANCEL)}")],

        map_to_parent={
            SETTINGS: SETTINGS,
            ConversationHandler.TIMEOUT: ConversationHandler.TIMEOUT,
            ConversationHandler.END: ConversationHandler.END
        },
        conversation_timeout=30
    )

    settings_handler = ConversationHandler(
        entry_points=[CommandHandler('settings', settings)],

        states={
            SETTINGS: [add_favourite_handler, remove_favourite_handler],
            CANCEL: [CallbackQueryHandler(cancel, pattern=f'{str(CANCEL)}')],
            ConversationHandler.TIMEOUT: [MessageHandler(Filters.all, timeout),
                                          CallbackQueryHandler(timeout)],
        },

        fallbacks=[CommandHandler('cancel', cancel),
                   CallbackQueryHandler(cancel, pattern=f"{str(CANCEL)}")],

        conversation_timeout=30,
        allow_reentry=True
    )

    job.run_daily(check_bus_data, time(19))

    dispatcher.add_handler(command_handler)
    dispatcher.add_handler(settings_handler)
    dispatcher.add_handler(search_location_or_postal_handler)
    dispatcher.add_handler(search_text_location_handler)
    dispatcher.add_handler(search_text_page_handler)
    dispatcher.add_handler(bus_service_handler)
    dispatcher.add_handler(bus_route_handler)
    dispatcher.add_handler(bus_handler)
    dispatcher.add_handler(bus_postal_handler)
    dispatcher.add_handler(refresh_handler)
    dispatcher.add_handler(unknown_handler)
    dispatcher.add_error_handler(error_callback)

    updater.start_polling(timeout=30)
    updater.idle()


if __name__ == '__main__':
    main()
