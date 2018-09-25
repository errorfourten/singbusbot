import json, requests, urllib,  pickle, os, sqlite3, shelve

#LTA API key needed to access the bus stop data from myTransport Datamall
#LTA_Account_Key = os.getenv("LTA_Account_Key")
LTA_Account_Key = os.getenv("LTA_Account_Key")

def updateBusStop():
    #Initialises array variables
    toAddCode = []
    toAddGPS = []

    for i in range(0,10): #Iterate through all data points
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
            toAddCode.append([x["BusStopCode"], x["Description"]])
            toAddGPS.append((x["Latitude"], x["Longitude"]))

    out = [toAddCode, toAddGPS]

    #Dump toAdd to a txt file for future use
    with open("busStop.txt", "wb") as outfile:
        pickle.dump(out, outfile)

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

def main():
    updateBusStop()
    updateBusService()

main()
