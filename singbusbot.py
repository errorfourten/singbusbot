import telegram, json, requests, time, urllib, datetime, updateBusData, pickle, os, sys, telegramCommands, logging, psycopg2
from telegram import *
from telegram.ext import *
from telegram.error import *
from urllib import parse

#Initialise private variables. Configured through environmental variables
TOKEN = os.getenv("TOKEN")
LTA_Account_Key = os.getenv("LTA_Account_Key")
owner_id = os.getenv("owner_id")
URL = "https://api.telegram.org/bot{}/".format(TOKEN)

#Connect to Postgres Database in Heroku
parse.uses_netloc.append("postgres")
url = parse.urlparse(os.environ["DATABASE_URL"])

conn = psycopg2.connect(
    database=url.path[1:],
    user=url.username,
    password=url.password,
    host=url.hostname,
    port=url.port
)
cur = conn.cursor()

#Creates a table in the database if it does not exist
cur.execute("CREATE TABLE IF NOT EXISTS user_data(user_id TEXT, username TEXT, first_name TEXT, favourite TEXT, state int, PRIMARY KEY (user_id));")
conn.commit()

#Start telegram wrapper & initate logging module
updater = Updater(token=TOKEN)
job = updater.job_queue
dispatcher = updater.dispatcher

#Adds a Filter to filter out the telegram TimedOut Errors
class TimedOutFilter(logging.Filter):
    def filter(self, record):
        if "Error while getting Updates: Timed out" in record.getMessage():
            return False

#Handles any commands
def commands(bot, update):
    text = telegramCommands.check_commands(bot, update, update.message.text)
    if '/broadcast' in update.message.text and update.message.from_user.id == int(owner_id):
        #Broadcasts messages if user is the owner
        cur.execute('''SELECT * FROM user_data WHERE state = 1''')
        row = cur.fetchall()
        for x in row:
            chat_id = json.loads(x[0])
            try: #Try to send a message to the user. If the user has blocked the bot, just skip
                bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
            except:
                pass
        logging.info("Broadcast complete")
    else:
        if update.message.text == '/start':
            #Adds a new row of data for new users
            cur.execute('''INSERT INTO user_data (user_id, username, first_name, favourite, state) VALUES ('%s', %s, %s, %s, 1) ON CONFLICT (user_id) DO UPDATE SET state = 1''', (update.message.from_user.id, update.message.from_user.username, update.message.from_user.first_name, '[]'))
            conn.commit()
        elif '/stop' in update.message.text:
            cur.execute('''UPDATE user_data SET state = 0 WHERE user_id = '%s' ''', (update.message.from_user.id,))
            conn.commit()
        elif text == False:
            logging.info("Invalid Command: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id, update.message.text)
            bot.send_message(chat_id=update.message.chat_id, text="Please enter a valid command", parse_mode="HTML")

        #Logs and sends message
        logging.info("Command: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id, update.message.text)
        bot.send_message(chat_id=update.message.chat_id, text=text, parse_mode="HTML")

#Handles invalid commands & logs request
def unknown(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text="Please enter a valid command")
    logging.info("Invalid command: %s [%s] (%s)", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id)

def error_callback(bot, update, error):
    if TimedOut:
        return
    else:
        logging.warning('Update "%s" caused error "%s"', update, error)

def send_message_to_owner(bot, update):
    bot.send_message(chat_id=owner_id, text=update)

def check_valid_bus_stop(message):
    if message == False:
        return (False, False)
    #Converts message to a processable form
    message = "".join([x for x in message if x.isalnum()]).lower()
    #Loads bus stop database from busStop.txt
    with open("busStop.txt", "rb") as afile:
        busStopDB = pickle.load(afile)
    flag=0

    #For each bus stop in the database, check if passed message is found
    for sublist in busStopDB:
        busStopName = "".join([y for y in sublist[1] if y.isalnum()]).lower()
        #Check for bus stop number or stop name
        if (message in sublist) or (message == busStopName):
            return (sublist[0], sublist[1]) #Return bus stop details - bus stop code, bus stop name
            flag = 1
            break

    #If none, return False
    if flag!=1:
        return (False, False)

def get_time(service): #Pass pjson data to return timeLeft and timeFollowingLeft

    if (service["NextBus"]["EstimatedArrival"].split("+")[0] == ""):
        return "NA", "NA" #If next bus timing does not exist, return NA
    else:
        nextBusTime = datetime.datetime.strptime(service["NextBus"]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S") #Get next bus timing
        try:
            followingBusTime = datetime.datetime.strptime(service["NextBus2"]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S")
        except:
            followingBusTime = "NA"

        currentTime = (datetime.datetime.utcnow()+datetime.timedelta(hours=8)).replace(microsecond=0)
        if currentTime > nextBusTime: #If API messes up, return following bus timing
            nextBusTime = datetime.datetime.strptime(service["NextBus2"]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S")
            try:
                followingBusTime = datetime.datetime.strptime(service["NextBus3"]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S")
            except:
                followingBusTime = "NA"

        timeLeft = str((nextBusTime - currentTime)).split(":")[1] #Return time next for next bus
        if followingBusTime != "NA":
            timeFollowingLeft = str((followingBusTime - currentTime)).split(":")[1] #Else, return time left for following bus
        else:
            timeFollowingLeft = followingBusTime
        return timeLeft, timeFollowingLeft

def check_valid_favourite(update):
    user = update.message.chat.id
    message = update.message.text
    cur.execute('''SELECT * FROM user_data WHERE '%s' = user_id''', (update.message.from_user.id,))
    row = cur.fetchall()
    if row == []:
        sf = []
    else:
        sf = json.loads(row[0][3])
    for x in sf:
    	isit = message in x[0]
    	if isit == True:
    		return x[1]
    return message

def send_bus_timings(bot, update, isCallback=False):
    #Replies user based on updates received
    text = ""

    #Assign message variable depending on request type
    if isCallback == True:
        CallbackQuery = update.callback_query
        message = CallbackQuery.message.text.split()[0]
    else:
        #Check if it exists in user's favourites
        message = check_valid_favourite(update)

    #Call function and assign to variables
    busStopCode, busStopName = check_valid_bus_stop(message)

    if busStopCode == False:
        #Informs the user that busStopCode was invalid & logs it
        bot.send_message(chat_id=update.message.chat_id, text="Please enter a valid bus stop code", parse_mode="Markdown")
        logging.info("Invalid request: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id, message)
        return

    else:
        header = "*{} - {}*\n".format(busStopCode,busStopName)
        text += header

        #HTTP Request to check bus timings
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2?BusStopCode="
        url += busStopCode
        request = urllib.request.Request(url)
        request.add_header('AccountKey', LTA_Account_Key)
        response = urllib.request.urlopen(request)
        pjson = json.loads(response.read().decode("utf-8"))

        #For each bus service that is returned
        for service in pjson["Services"]:
            timeLeft, timeFollowingLeft = get_time(service)

            #Display time left for each service
            text += service["ServiceNo"]+"    "
            if (timeLeft == "00"):
                text += "Arr"
            else:
                text += timeLeft+" min"
            text += "    "
            if (timeFollowingLeft == "00"):
                text += "Arr"
            else:
                text += timeFollowingLeft+" min"
            text += "\n"


        if (text == header): #If no results were returned
            text += "No more buses at this hour"
    #Format of inline refresh button
    button_list = [
        [
            InlineKeyboardButton("Refresh", callback_data="Hey")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(button_list)

    #If it's a callback function,
    if isCallback == True:
        #Reply to the user and log it
        text += "\n_Last Refreshed: " + (datetime.datetime.utcnow()+datetime.timedelta(hours=8)).strftime('%H:%M:%S') + "_"
        logging.info("Refresh: %s [%s] (%s), %s", CallbackQuery.from_user.first_name, CallbackQuery.from_user.username, CallbackQuery.from_user.id, message)
        bot.editMessageText(chat_id=CallbackQuery.message.chat_id, message_id=CallbackQuery.message.message_id, text=text, parse_mode="Markdown", reply_markup=reply_markup)
        bot.answerCallbackQuery(callback_query_id=CallbackQuery.id)

    #Else, send a new message
    else:
        logging.info("Request: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id, message)
        bot.send_message(chat_id=update.message.chat_id, text=text, parse_mode="Markdown", reply_markup=reply_markup)

def refresh_timings(bot, update):
    send_bus_timings(bot, update, isCallback=True)

def update_bus_data(bot, update):
    updateBusData.main()
    logging.info("Updated Bus Data")

class FilterBusService(BaseFilter): #Create a new telegram filter, filter out bus Services
    def filter(self, message):
        with open("busServiceNo.txt", "rb") as afile:
            busServiceNo = pickle.load(afile)
        return message.text in busServiceNo

busService_filter = FilterBusService()

#ConversationHandler for bus services

BUSSERVICE = range(1)

def askBusRoute(bot, update, user_data): #Takes in bus service and outputs direction, waiting for user's confirmation
    busNumber = update.message.text

    with open("busService.txt", "rb") as afile:
        busServiceDB = pickle.load(afile)

    out = [element for element in busServiceDB if element['serviceNo'] == busNumber] #Find the direction(s) out that bus service
    reply_keyboard = []
    for x in range(len(out)): #Generates a reply_keyboard with the directions
        busStopCodeStart, busStopNameStart = check_valid_bus_stop(out[x]["BusStopCode"][0])
        busStopCodeEnd, busStopNameEnd = check_valid_bus_stop(out[x]["BusStopCode"][-1])
        st = "%s - %s" % (busStopNameStart, busStopNameEnd)
        text = [st]
        reply_keyboard.append(text)
    user_data["busService"] = [busNumber, reply_keyboard] #Pass the generated data to user_data
    update.message.reply_text("Which direction?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)) #Asks user for input
    logging.info("Service Request: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id, busNumber)

    return BUSSERVICE

def sendTyping(bot, job):
    bot.send_chat_action(chat_id=job.context, action="typing", timeout=30)

def findBusRoute(bot, update, user_data): #Once user has replied with direction, output the arrival timings
    job_sendTyping = job.run_repeating(sendTyping, interval = 5, first=0, context=update.message.from_user.id)
    reply = update.message.text

    #Create the usual reply_keyboard
    sf = fetch_user_data(update)
    reply_keyboard = generate_reply_keyboard(sf)

    if [reply] in user_data["busService"][1]: #Ensures that the user reply is a valid one
        direction = user_data["busService"][1].index([reply]) #Gets the direction in terms of a int
        busNumber = user_data["busService"][0]

        with open("busService.txt", "rb") as afile:
            busServiceDB = pickle.load(afile)

        out = [element for element in busServiceDB if element['serviceNo'] == busNumber] #Gets all directions of bus service
        header = "Bus %s (%s)\n" % (str(busNumber), reply)
        message = "<i>%s</i>" % header

        for busStopCode in out[direction]["BusStopCode"]: #For every bus stop code in that direction
            url = "http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2?BusStopCode="
            url += busStopCode
            request = urllib.request.Request(url)
            request.add_header('AccountKey', LTA_Account_Key)
            response = urllib.request.urlopen(request)
            pjson = json.loads(response.read().decode("utf-8")) #Get the raw data from LTA

            service = [element for element in pjson["Services"] if element['ServiceNo'] == busNumber] #Select the correct bus service from raw data
            if service == []: #If there are no more buses for the day
                message += "No more buses at this hour"
                break
            else: #Else, return the timings
                timeLeft, timeFollowingLeft = get_time(service[0]) #and gets the arrival time
                busStopCode, busStopName = check_valid_bus_stop(busStopCode)
                text = "<b>" + busStopName + "</b>   "
                if timeLeft == "00":
                    text += "Arr"
                else:
                    text += timeLeft + " min"
                message += text + "\n"
            logging.info(timeLeft)
        job_sendTyping.schedule_removal()
        update.message.reply_text(message, reply_markup=ReplyKeyboardMarkup(reply_keyboard), parse_mode="HTML")
        logging.info("Service Request: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id, header)
    else:
        job_sendTyping.schedule_removal()
        update.message.reply_text("Invalid direction", reply_markup=ReplyKeyboardMarkup(reply_keyboard), parse_mode="HTML")
        logging.info("Invalid direction: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id, reply)
    user_data.clear()
    return ConversationHandler.END

#Initialise some variables for the service ConversationHandler function
ADD, NAME, POSITION, CONFIRM, REMOVE, REMOVECONFIRM = range(6)

def generate_reply_keyboard(sf):
    i=1
    temp=[]
    reply_keyboard=[]
    for x in sf:
        temp.append(x[0])
        if i%2==0:
        	reply_keyboard.append(temp)
        	temp=[]
        if (i%2==1 and i == len(sf)):
            reply_keyboard.append(temp)
        i+=1
    return reply_keyboard

def fetch_user_data(update):
    cur.execute('''SELECT * FROM user_data WHERE '%s' = user_id''', (update.message.from_user.id, ))
    conn.commit()
    row = cur.fetchall()
    if row == []:
        sf = []
    else:
        sf = json.loads(row[0][3])
    return sf

#Settings menu
def settings(bot, update, user_data):
    logging.info("Accessing settings: %s [%s] (%s)", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id)
    sf = fetch_user_data(update)

    #If user has no favourites, no remove option will be given
    if sf == []:
        reply_keyboard = [["Add Favourite"]]
    else:
        reply_keyboard = [["Add Favourite", "Remove Favourite"]]
    update.message.reply_text(
        "What would you like to do?\n"
        "Send /cancel to stop this at any time", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)
        )
    return ADD

def add_favourite(bot, update, user_data):
    user_data.clear()
    update.message.reply_text("Please enter a bus stop code")
    return NAME

def choose_name(bot, update, user_data):
    message = update.message.text
    busStopCode, busStopName = check_valid_bus_stop(message)

    if busStopCode == False:
        #Informs the user that busStopCode was invalid & logs it
        update.message.reply_text("Try again. Please enter a valid bus stop code")
        return ADD

    else:
        user_data["busStopCode"] = busStopCode
        update.message.reply_text("What would you like to name: {} - {}?".format(busStopCode, busStopName))
        return POSITION

#Asks user to confirm favourite
def to_confirm(bot, update, user_data):
    user_data["name"] = update.message.text
    reply_keyboard = [["Yes", "No"]]
    update.message.reply_text("Please confirm that you would like to add {} - {}".format(user_data["name"], user_data["busStopCode"]), reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True))
    return CONFIRM

#Adds favourite into database
def confirm_favourite(bot, update, user_data):

    #Fetches data from database
    sf = fetch_user_data(update)
    user_data["sf"] = sf

    #Adds new favourite to the list
    sf.append([user_data["name"], user_data["busStopCode"]])
    insert_sf = json.dumps(sf)
    cur.execute('''INSERT INTO user_data (user_id, username, first_name, favourite, state) VALUES ('%s', %s, %s, %s, 1) ON CONFLICT (user_id) DO UPDATE SET favourite = %s; ''', (update.message.from_user.id, update.message.from_user.username, update.message.from_user.first_name, insert_sf, insert_sf))
    conn.commit()

    reply_keyboard = generate_reply_keyboard(sf)

    logging.info("Added New Favourite: %s [%s] (%s)", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id)
    update.message.reply_text("Added!", reply_markup=ReplyKeyboardMarkup(reply_keyboard))
    user_data.clear()
    return ConversationHandler.END

def remove_favourite(bot, update, user_data):
    user_data.clear()

    #Gets data from database
    sf = fetch_user_data(update)
    user_data["sf"] = sf

    reply_keyboard = generate_reply_keyboard(sf)

    update.message.reply_text("What bus stop would you like to remove?", reply_markup=ReplyKeyboardMarkup(reply_keyboard))
    return REMOVE

#Asks user to confirm removing bus stop
def to_remove(bot, update, user_data):
    sf = user_data["sf"]
    for x in sf:
        if update.message.text in x:
            index = sf.index(x)
    to_remove = sf[index]
    user_data["remove"] = to_remove

    reply_keyboard = [["Yes", "No"]]
    update.message.reply_text("Are you sure you want to remove {} - {}?".format(to_remove[0], to_remove[1]), reply_markup=ReplyKeyboardMarkup(reply_keyboard), one_time_keyboard=True)
    return REMOVECONFIRM

def confirm_remove(bot, update, user_data):
    #Inserts the new list into the database
    user_data["sf"].remove(user_data["remove"])
    sf = user_data["sf"]
    insert_sf = json.dumps(sf)
    cur.execute('''UPDATE user_data SET favourite = %s WHERE user_id = '%s' ''', (insert_sf, update.message.from_user.id))
    conn.commit()

    reply_keyboard = generate_reply_keyboard(sf)

    logging.info("Removed favourite: %s [%s] (%s)", update.message.from_user.first_name, update.message.from_user.username, update.message.from_user.id)
    update.message.reply_text("Removed!", reply_markup=ReplyKeyboardMarkup(reply_keyboard))
    return ConversationHandler.END

#Allows user to quit at anytime
def cancel(bot, update, user_data):
    #Generates reply_keyboard
    sf = fetch_user_data(update)

    reply_keyboard = generate_reply_keyboard(sf)

    update.message.reply_text("Ended", reply_markup=ReplyKeyboardMarkup(reply_keyboard))
    user_data.clear()
    return ConversationHandler.END

def main():
    telegram_logger = logging.getLogger('telegram.ext.updater')
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    telegram_logger.addFilter(TimedOutFilter())

    command_handler = MessageHandler(Filters.command, commands)
    refresh_handler = CallbackQueryHandler(refresh_timings)
    bus_handler = MessageHandler(Filters.text, send_bus_timings)
    unknown_handler = MessageHandler(Filters.all, unknown)

    busService_handler = ConversationHandler(
        entry_points=[MessageHandler(busService_filter, askBusRoute, pass_user_data=True)],

        states={
            BUSSERVICE: [MessageHandler(Filters.text, findBusRoute, pass_user_data=True)]
        },

        fallbacks=[CommandHandler("cancel",cancel, pass_user_data=True)],
        conversation_timeout = 60
    )

    settings_handler = ConversationHandler(
        entry_points=[CommandHandler('settings', settings, pass_user_data=True)],

        states={
            ADD: [RegexHandler("^Add Favourite$", add_favourite, pass_user_data=True), RegexHandler("^Remove Favourite$", remove_favourite, pass_user_data=True)],
            NAME: [MessageHandler(Filters.text, choose_name, pass_user_data=True)],
            POSITION: [MessageHandler(Filters.text, to_confirm, pass_user_data=True)],
            CONFIRM: [RegexHandler("Yes", confirm_favourite, pass_user_data=True), RegexHandler("No", add_favourite, pass_user_data=True)],
            REMOVE: [MessageHandler(Filters.text, to_remove, pass_user_data=True)],
            REMOVECONFIRM: [RegexHandler("Yes", confirm_remove, pass_user_data=True), RegexHandler("No", cancel, pass_user_data=True)]
        },

        fallbacks=[CommandHandler("cancel",cancel, pass_user_data=True)],
        allow_reentry = True,
        conversation_timeout = 60
    )

    job.run_daily(update_bus_data, datetime.time(19))
    dispatcher.add_handler(settings_handler)
    dispatcher.add_handler(refresh_handler)
    dispatcher.add_handler(busService_handler)
    dispatcher.add_handler(command_handler)
    dispatcher.add_handler(bus_handler)
    dispatcher.add_handler(unknown_handler)
    dispatcher.add_error_handler(error_callback)

    updater.start_polling(timeout=30)
    updater.idle()

if __name__ == '__main__':
    main()
