import json, requests, time, urllib, datetime, updateBusData, pickle, os

TOKEN = os.getenv("TOKEN")
LTA_Account_Key = os.getenv("LTA_Account_Key")
URL = "https://api.telegram.org/bot{}/".format(TOKEN)

def get_url(url):
    response = requests.get(url)
    content = response.content.decode("utf8")
    return content

def get_json(url):
    content = get_url(url)
    js = json.loads(content)
    return js

def get_updates(offset=None):
    url = URL + "getUpdates"
    if offset:
        url += "?offset={}".format(offset)
    js = get_json(url)
    return js

def get_last_update_id(updates):
    update_ids = []
    for update in updates["result"]:
        update_ids.append(int(update["update_id"]))
    return max(update_ids)

def check_valid_bus_stop(busStopCode):
    with open("busStop.txt", "rb") as afile:
        busStop = pickle.load(afile)
    flag=0
    for sublist in busStop:
        if busStopCode in sublist:
            return sublist[1]
            flag = 1
            break
    if flag!=1:
        return False

def send_bus_timings(updates):
    #Check myDatamall
    text = ""
    for update in updates["result"]:
        try:
            busStopCode = update["message"]["text"]
            chat_id = update["message"]["chat"]["id"]
        except KeyError:
            busStopCode = update["edited_message"]["text"]
            chat_id = update["edited_message"]["chat"]["id"]

        busStopName = check_valid_bus_stop(busStopCode)
        if busStopName == False:
            text = "Please enter a valid bus stop code"
        else:
            text += busStopCode + " - " + busStopName
            url = "http://datamall2.mytransport.sg/ltaodataservice/BusArrivalv2?BusStopCode="
            url += busStopCode
            request = urllib.request.Request(url)
            request.add_header('AccountKey', LTA_Account_Key)
            response = urllib.request.urlopen(request)
            pjson = json.loads(response.read().decode("utf-8"))
            x = 0

            for service in pjson["Services"]:
                nextBusTime = datetime.datetime.strptime(pjson["Services"][x]["NextBus"]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S")
                currentTime = (datetime.datetime.utcnow()+datetime.timedelta(hours=8)).replace(microsecond=0)
                if currentTime > nextBusTime:
                    nextBusTime = datetime.datetime.strptime(pjson["Services"][x]["NextBus2"]["EstimatedArrival"].split("+")[0], "%Y-%m-%dT%H:%M:%S")
                timeLeft = str((nextBusTime - currentTime)).split(":")[1]

                if (timeLeft == "00"):
                    text += service["ServiceNo"]+"    "+"Arr"+"\n"
                else:
                    text += service["ServiceNo"]+"    "+timeLeft+" min"+"\n"
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
    url = URL + "sendMessage?text={}&chat_id={}".format(text, chat_id)
    get_url(url)

def main():
    last_update_id = None
    while True:
        if datetime.datetime.now().hour == 0:
            updateBusData.main()

        updates = get_updates(last_update_id)
        if len(updates["result"]) > 0:
            last_update_id = get_last_update_id(updates) + 1
            send_bus_timings(updates)
        time.sleep(0.5)

if __name__ == '__main__':
    main()
