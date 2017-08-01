import json, requests, urllib, pickle, os

#LTA API key needed to access the bus stop data from myTransport Datamall
LTA_Account_Key = os.getenv("LTA_Account_Key")

def updateBusStop():
    toAdd = []

    #Set arbitary range to access all bus stops as API only passes a max of 50 bus stops per call
    for i in range(0, 101):
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusStops?$skip="
        url += str(i*50)

        #HTTP request
        request = urllib.request.Request(url)
        request.add_header('AccountKey', LTA_Account_Key)
        response = urllib.request.urlopen(request)
        pjson = json.loads(response.read().decode("utf-8"))

        #For every row of data, add data to a txt file
        for i in range(len(pjson["value"])):
            x = pjson["value"][i]
            toAdd.append([x["BusStopCode"], x["Description"], x["RoadName"], x["Latitude"], x["Longitude"]])

    #Dump toAdd to a txt file for future use
    with open("busStop.txt", "wb") as outfile:
        pickle.dump(toAdd, outfile)

def main():
    updateBusStop()
