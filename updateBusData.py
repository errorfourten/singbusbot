import json, requests, urllib, pickle, os

LTA_Account_Key = os.getenv("LTA_Account_Key")

def updateBusStop():
    toAdd = []
    for i in range(0, 101):
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusStops?$skip="
        url += str(i*50)
        #print(url)
        request = urllib.request.Request(url)
        request.add_header('AccountKey', LTA_Account_Key)
        response = urllib.request.urlopen(request)
        pjson = json.loads(response.read().decode("utf-8"))
        for i in range(len(pjson["value"])):
            x = pjson["value"][i]
            #print(x["Description"])
            toAdd.append([x["BusStopCode"], x["Description"], x["RoadName"], x["Latitude"], x["Longitude"]])
    with open("busStop.txt", "wb") as outfile:
        pickle.dump(toAdd, outfile)

def main():
    updateBusStop()
