import requests
import pickle
import os

# LTA API key needed to access the bus stop data from myTransport Datamall
LTA_ACCOUNT_KEY = os.getenv("LTA_Account_Key")


def update_bus_stop_db():
    """
    Gets all the bus stops from the LTA API and saves it as a DB

    :return: [ [ [BusStopCode, Description], ... ], [ [Latitude, Longitude], ... ] ]
    """
    # Initialises array variables
    to_add_stop = []
    to_add_gps = []

    pjson_len, i = 500, 0

    while pjson_len == 500:
        url = f"http://datamall2.mytransport.sg/ltaodataservice/BusStops?$skip={i*500}"
        headers = {'AccountKey': LTA_ACCOUNT_KEY}
        r = requests.get(url, headers=headers)
        pjson = r.json()

        for bus_stop in pjson["value"]:
            to_add_stop.append([bus_stop["BusStopCode"], bus_stop["Description"]])
            to_add_gps.append([bus_stop["Latitude"], bus_stop["Longitude"]])

        pjson_len = len(pjson["value"])
        i += 1

    out = [to_add_stop, to_add_gps]
    with open("busStop.txt", "wb") as outfile:
        pickle.dump(out, outfile)


def update_bus_service_db():
    """
    Gets all the bus services from the LTA API and saves it as a DB

    :return: busServiceNo: Set of all the different bus numbers
    :return: busService: [{"service_no": ..., "direction": ..., "bus_stops": ...}, ...]
    """
    tempdict = {}
    bus_services = []
    bus_service_nos = set()
    active_service = ""

    pjson_len, i = 500, 0

    while pjson_len == 500:     # While there are still services left to be processed
        url = f"http://datamall2.mytransport.sg/ltaodataservice/BusRoutes?$skip={i*500}"
        headers = {'AccountKey': LTA_ACCOUNT_KEY}
        r = requests.get(url, headers=headers)
        pjson = r.json()

        for service in pjson["value"]:
            current_service = f'{str(service["ServiceNo"])}_{str(service["Direction"])}'    # Get the returned service

            if current_service != active_service:
                if not active_service == "":
                    bus_services.append(tempdict)        # If it's a new service, append the previous service

                tempdict = {"service_no": str(service["ServiceNo"]),
                            "direction": str(service["Direction"]), "bus_stops": []}
                active_service = current_service

            bus_service_nos.add(service["ServiceNo"])       # Add bus numbers to the set
            tempdict["bus_stops"].append(service["BusStopCode"])       # Add bus stop code for every service

        pjson_len = len(pjson["value"])
        i += 1

    bus_services.append(tempdict)  # Append the very last service

    with open("busServiceNo.txt", "wb") as outfile:
        pickle.dump(bus_service_nos, outfile)
    with open("busService.txt", "wb") as outfile:
        pickle.dump(bus_services, outfile)


def main():
    update_bus_stop_db()
    update_bus_service_db()


if __name__ == '__main__':
    main()
