import requests
import pickle
import os

# LTA API key needed to access the bus stop data from myTransport Datamall
LTA_ACCOUNT_KEY = os.getenv("LTA_Account_Key")


def get_bus_stop_data():
    """
    Gets all the bus stops from the LTA API and returns it in a list

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
            to_add_stop.append((bus_stop["BusStopCode"], bus_stop["Description"]))
            to_add_gps.append((bus_stop["Latitude"], bus_stop["Longitude"]))

        pjson_len = len(pjson["value"])
        i += 1

    data = [to_add_stop, to_add_gps]
    return data


def get_bus_service_data():
    """
    Gets all the bus services from the LTA API and returns it in a list

    :return: busServiceNo: Set of all the different bus numbers
    :return: busService: [{"service_no": ..., "direction": ..., "bus_stops": ...}, ...]
    """
    tempdict = {}
    bus_services = []
    bus_service_nos = list()
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

            bus_service_nos.append(service["ServiceNo"])       # Add bus numbers to the set
            tempdict["bus_stops"].append(service["BusStopCode"])       # Add bus stop code for every service

        pjson_len = len(pjson["value"])
        i += 1

    bus_services.append(tempdict)  # Append the very last service
    return bus_service_nos, bus_services


def check_bus_data():
    """
    Checks saved data on file compared with current data from the API.
    :return: Booleans based on bus_stop_data, bus_services_nos, bus_services
    """
    with open("busStop.txt", "rb") as file:
        saved_bus_stop_data = pickle.load(file)
    with open("busServiceNo.txt", "rb") as file:
        saved_bus_service_nos = pickle.load(file)
    with open("busService.txt", "rb") as file:
        saved_bus_services = pickle.load(file)

    current_bus_stop_data = get_bus_stop_data()
    current_bus_service_nos, current_bus_services = get_bus_service_data()

    return current_bus_stop_data == saved_bus_stop_data, current_bus_service_nos == saved_bus_service_nos, \
        current_bus_services == saved_bus_services


def save_bus_data():
    """
    Saves the bus data to a pickle file on disk
    """
    bus_stop_data = get_bus_stop_data()
    bus_service_nos, bus_services = get_bus_service_data()

    with open("busStop.pkl", "wb") as outfile:
        pickle.dump(bus_stop_data, outfile)
    with open("busServiceNo.pkl", "wb") as outfile:
        pickle.dump(bus_service_nos, outfile)
    with open("busService.pkl", "wb") as outfile:
        pickle.dump(bus_services, outfile)


if __name__ == '__main__':
    save_bus_data()
