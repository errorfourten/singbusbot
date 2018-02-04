import telegram, json, requests, time, urllib, datetime, updateBusData, pickle, os, sys, telegramCommands, logging
from telegram import InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, InlineQueryHandler, CallbackQueryHandler
from telegram.error import TelegramError, Unauthorized, BadRequest, TimedOut, ChatMigrated, NetworkError

#Initialise private variables. Configured through environmental variables
TOKEN = os.getenv("TOKEN")
LTA_Account_Key = os.getenv("LTA_Account_Key")
owner_id = os.getenv("owner_id")
URL = "https://api.telegram.org/bot{}/".format(TOKEN)

#Start telegram wrapper & initate logging module
updater = Updater(token=TOKEN)
job = updater.job_queue
dispatcher = updater.dispatcher

class TimedOutFilter(logging.Filter):
    def filter(self, record):
        if "Error while getting Updates: Timed out" in record.getMessage():
            return False

#Handles /start commands
def commands(bot, update):
    text = telegramCommands.check_commands(bot, update, update.message.text)
    logging.info("Command: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.chat_id, update.message.text)
    bot.send_message(chat_id=update.message.chat_id, text=text, parse_mode="HTML")

#Handles invalid commands & logs request
def unknown(bot, update):
    bot.send_message(chat_id=update.message.chat_id, text="Please enter a valid command")
    logging.info("Invalid command: %s [%s] (%s)", update.message.from_user.first_name, update.message.from_user.username, update.message.chat_id)

def error_callback(bot, update, error):
    if TimedOut:
        return
    else:
        logging.warning('Update "%s" caused error "%s"', update, error)

def send_message_to_owner(bot, update):
    bot.send_message(chat_id=owner_id, text=update)

def check_valid_bus_stop(message):
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

def get_time(pjson, x, NextBus):
    return datetime.datetime.strptime(pjson["Services"][x][NextBus]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S")

def send_bus_timings(bot, update, isCallback=False):
    #Replies user based on updates received
    text = ""

    #Assign message variable depending on request type
    if isCallback == True:
        CallbackQuery = update.callback_query
        message = CallbackQuery.message.text.split()[0]
    else:
        message = update.message.text

    #Call function and assign to variables
    busStopCode, busStopName = check_valid_bus_stop(message)

    if busStopCode == False:
        #Informs the user that busStopCode was invalid & logs it
        bot.send_message(chat_id=update.message.chat_id, text="Please enter a valid bus stop code", parse_mode="Markdown")
        logging.info("Invalid request: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.chat_id, message)
        return

    else:
        text += "*{} - {}*\n".format(busStopCode,busStopName)

        #HTTP Request to check bus timings
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2?BusStopCode="
        url += busStopCode
        request = urllib.request.Request(url)
        request.add_header('AccountKey', LTA_Account_Key)
        response = urllib.request.urlopen(request)
        pjson = json.loads(response.read().decode("utf-8"))
        x = 0

        #For each bus service that is returned
        for service in pjson["Services"]:
            nextBusTime = get_time(pjson, x, "NextBus") #Get next bus timing
            try:
                followingBusTime = get_time(pjson, x, "NextBus2") # Get following bus timing
            except:
                followingBusTime = False #If there is no following bus timiing, skip
            currentTime = (datetime.datetime.utcnow()+datetime.timedelta(hours=8)).replace(microsecond=0) #Get current GMT +8 time
            if currentTime > nextBusTime: #If API messes up, return next 2 bus timings instead
                nextBusTime = get_time(pjson, x, "NextBus2")
                try:
                    followingBusTime = get_time(pjson, x, "NextBus3")
                except:
                    followingBusTime = False
            timeLeft = str((nextBusTime - currentTime)).split(":")[1] #Return time next for next bus

            if followingBusTime == False: #If there is no bus arriving, display NA
                timeFollowingLeft = "NA"
            else:
                timeFollowingLeft = str((followingBusTime - currentTime)).split(":")[1] #Else, return time left for following bus

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

            x+=1

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
        logging.info("Refresh: %s [%s] (%s), %s", CallbackQuery.from_user.first_name, CallbackQuery.from_user.username, CallbackQuery.message.chat_id, message)
        bot.editMessageText(chat_id=CallbackQuery.message.chat_id, message_id=CallbackQuery.message.message_id, text=text, parse_mode="Markdown", reply_markup=reply_markup)
        bot.answerCallbackQuery(callback_query_id=CallbackQuery.id)

    #Else, send a new message
    else:
        logging.info("Request: %s [%s] (%s), %s", update.message.from_user.first_name, update.message.from_user.username, update.message.chat_id, message)
        bot.send_message(chat_id=update.message.chat_id, text=text, parse_mode="Markdown", reply_markup=reply_markup)

def refresh_timings(bot, update):
    send_bus_timings(bot, update, isCallback=True)

def update_bus_data(bot, update):
    updateBusData.main()
    logging.info("Updated Bus Data")

def main():
    telegram_logger = logging.getLogger('telegram.ext.updater')
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    telegram_logger.addFilter(TimedOutFilter())

    command_handler = MessageHandler(Filters.command, commands)
    refresh_handler = CallbackQueryHandler(refresh_timings)
    bus_handler = MessageHandler(Filters.text, send_bus_timings)
    unknown_handler = MessageHandler(Filters.all, unknown)

    job.run_daily(update_bus_data, datetime.time(3))
    dispatcher.add_handler(command_handler)
    dispatcher.add_handler(refresh_handler)
    dispatcher.add_handler(bus_handler)
    dispatcher.add_handler(unknown_handler)
    dispatcher.add_error_handler(error_callback)

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
