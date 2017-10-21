import json, requests, urllib, pickle, os, sqlite3

#LTA API key needed to access the bus stop data from myTransport Datamall
LTA_Account_Key = "VtnRuFd7QgWLWklcMg1rRA=="

def updateBusStop():
    toAdd = []

    #Set arbitary range to access all bus stops as API only passes a max of 50 bus stops per call
    for i in range(0, 9):
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusStops?$skip="
        url += str(i*500)

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

def updateBusService():
    toAdd = []

    #Set arbitary range to access all bus stops as API only passes a max of 50 bus stops per call
    for i in range(0, 1):
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusRoutes?$skip="
        url += str(i*50)

        #HTTP request
        request = urllib.request.Request(url)
        request.add_header('AccountKey', LTA_Account_Key)
        response = urllib.request.urlopen(request)
        pjson = json.loads(response.read().decode("utf-8"))

        #For every row of data, add data to a txt file
        serviceNo = None
        direction = None
        busStops = []
        for i in range(len(pjson["value"])):
            x = pjson["value"][i]
            serviceNo = x["ServiceNo"]
            stop = x["StopSequence"] - 1

            if [serviceNo, x["Direction"]] in (item[0] for item in toAdd):
                print(toAdd)
                index = toAdd.index(item[0])
                if stop > toAdd[index][1][1]:
                    toAdd[index][1].append([x["BusStopCode"], stop])
                    toAdd[index][2].append([x["Distance"], stop])
                else:
                    toAdd[index][1].insert(0, [x["BusStopCode"], stop])
                    toAdd[index][2].insert(0, [x["Distance"], stop])

            else:
                toAdd.append([[serviceNo, x["Direction"]], [], []])
                toAdd[-1][1] = [x["BusStopCode"], stop]
                toAdd[-1][2] = [x["Distance"], stop]
                print([serviceNo, x["Direction"]])
                for item in toAdd:
                    print(item[0])

        #print(toAdd)
    #Dump toAdd to a txt file for future use
    with open("busService.txt", "wb") as outfile:
        pickle.dump(toAdd, outfile)

def main():
    updateBusStop()
    #updateBusService()

main()
