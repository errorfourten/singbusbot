import json, requests, urllib,  pickle, os, sqlite3, shelve

#LTA API key needed to access the bus stop data from myTransport Datamall
#LTA_Account_Key = os.getenv("LTA_Account_Key")
LTA_Account_Key = os.getenv("LTA_Account_Key")

def updateBusStop():
    toAdd = []

    #Set arbitary range to access all bus stops as API only passes a max of 500 bus stops per call
    for i in range(0, 10):
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
    ls = [] #Initialise busService list (database)
    ls2 = set([]) #Initialise busServiceNo list (list of buses)
    currentBus = ""

    for i in range(0,53): #Get all bus data from LTA API
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusRoutes?$skip="
        url += str(i*500)

        request = urllib.request.Request(url)
        request.add_header('AccountKey', "VtnRuFd7QgWLWklcMg1rRA==")
        response = urllib.request.urlopen(request)
        pjson = json.loads(response.read().decode("utf-8"))

        bus = pjson["value"]

        for x in range (len(pjson["value"])): #For number of data points for each API call
            serviceNo = str(bus[x]["ServiceNo"]) + "_" + str(bus[x]["Direction"]) #Get the serviceNo
            if serviceNo == currentBus: #If data point is the same serviceNo as the previous one
                templs.append(bus[x]["BusStopCode"]) #Add the bus service
                if x == len(pjson["value"])-1 and i == 52: #If this is the very last datapoint, add it
                    ls.append({"serviceNo":str(bus[x]["ServiceNo"]), "direction": bus[x]["Direction"], "BusStopCode": templs})
                    ls2.add(bus[x]["ServiceNo"])
            else: #Else, if this is a new bus
                if currentBus == "": #If this is the first datapoint, pass
                    pass
                else: #Append the previous busService to ls and busServiceNo to ls2
                    ls.append({"serviceNo":str(bus[x-1]["ServiceNo"]), "direction": bus[x-1]["Direction"], "BusStopCode": templs})
                    ls2.add(bus[x-1]["ServiceNo"])
                templs = [bus[x]["BusStopCode"]] #and the continue adding buses
                currentBus = serviceNo #and update the currentBus

    with open("busServiceNo.txt", "wb") as outfile:
        pickle.dump(list(ls2), outfile)
    with open("busService.txt", "wb") as outfile:
        pickle.dump(ls, outfile)

'''

def updateBusService():
    busStops = {}
    #Set arbitary range to access all bus stops as API only passes a max of 500 bus stops per call
    for i in range(0, 500):
        url = "http://datamall2.mytransport.sg/ltaodataservice/BusRoutes?$skip="
        url += str(i*500)

        #HTTP request
        request = urllib.request.Request(url)
        request.add_header('AccountKey', LTA_Account_Key)
        response = urllib.request.urlopen(request)
        pjson = json.loads(response.read().decode("utf-8"))

        #For every row of data, add data to a txt file

        serviceNo = None
        direction = None

        for j in range(len(pjson["value"])):
            x = pjson["value"][j]

            serviceNo = str(x["ServiceNo"])
            direction = str(x["Direction"])
            stop = x["StopSequence"] - 1
            busStopCode = x["BusStopCode"]
            distance = x["Distance"]

            busService = serviceNo+"_"+direction
            #print(busStops)
            if busStops.get(busService) == None:
                toAdd = [None]*150
                toAdd[stop] = [busStopCode, distance, x["WD_FirstBus"], x["WD_LastBus"], x["SAT_FirstBus"], x["SAT_LastBus"], x["SUN_FirstBus"], x["SUN_LastBus"]]
                busStops[busService] = toAdd
            else:
                toAdd = busStops.get(busService)
                toAdd[stop] = [busStopCode, distance]
                busStops[busService] = toAdd

    for key, value in busStops.items():

        value = [x for x in value if x is not None]
        busStops[key] = value

    #Dump toAdd to a txt file for future use
    with open("busService.txt", "wb") as outfile:
        pickle.dump(busStops, outfile)

    #myShelve = shelve.open('busService.txt')
    #myShelve.update(busStops)
    #myShelve.close()

'''

def main():
    updateBusStop()
    updateBusService()

main()
