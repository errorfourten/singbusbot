import json, requests, time, urllib, datetime, updateBusData, pickle, os, sys, telegramCommands

#Initialise private variables, TOKEN is API key for Telegram, LTA_Account_Key is for LTA API Key
TOKEN = os.getenv("TOKEN")
LTA_Account_Key = os.getenv("LTA_Account_Key")
URL = "https://api.telegram.org/bot{}/".format(TOKEN)

def get_json(url):
    #Standard HTTP request
    response = requests.get(url)
    content = response.content.decode("utf8")
    js = json.loads(content)
    return js

def get_updates(offset=None):
    #Get new messages from the Telegram API
    url = URL + "getUpdates"

    #offset is to clear any existing messages by passing the last update id received
    if offset:
        url += "?offset={}".format(offset)

    #Get update using URL
    js = get_json(url)
    return js

def get_last_update_id(updates):
    update_ids = []
    for update in updates["result"]:
        update_ids.append(int(update["update_id"]))
    return max(update_ids)

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

def send_bus_timings(updates):
    #Replies user based on updates received
    text = ""

    for update in updates["result"]:
        #Try to obtain the message & chat_id from the update

        try:
            message = update["message"]["text"]
            chat_id = update["message"]["chat"]["id"]
        #If message was updated after it was sent, exception catches it as message will be edited_message instead
        except KeyError:
            message = update["edited_message"]["text"]
            chat_id = update["edited_message"]["chat"]["id"]

        print("Request from: "+str(update["message"]["chat"])+", "+message)   #Output to system logs

        busStopCode, busStopName = check_valid_bus_stop(message)
        if busStopCode == False:
            #If it is not a valid bus stop, check if it is a command for the bot, if not return error
            text = telegramCommands.check_commands(message)
            if text == False:
                text = "Please enter a valid bus stop code"

        else:
            text += busStopCode + " - " + busStopName

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

    send_message(text, chat_id)

def get_last_chat(updates):
    num_updates = len(updates["result"])
    last_update = num_updates - 1
    text = updates["result"][last_update]["message"]["text"]
    chat_id = updates["result"][last_update]["message"]["chat"]["id"]
    return (text, chat_id)

def send_message(text, chat_id):
    text = urllib.parse.quote_plus(text)
    url = URL + "sendMessage?text={}&chat_id={}&parse_mode=Markdown".format(text, chat_id)
    get_url(url)

def main():
    last_update_id = None
    while True:
        #Update bus stop database every day at 12am
        if datetime.datetime.now().hour == 0:
            updateBusData.main()

        #Check for an update from Telegram every loop
        updates = get_updates(last_update_id)

        #If there is an update...
        if len(updates["result"]) > 0:
            #Update last_update_id to ensure the message is not processed again
            last_update_id = get_last_update_id(updates) + 1
            #Reply appropriately
            send_bus_timings(updates)
        sys.stdout.flush()
        time.sleep(0.5)

if __name__ == '__main__':
    main()
