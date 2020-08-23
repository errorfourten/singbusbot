import requests
import json
from datetime import datetime


def get_one_map_api_token(one_map_email, one_map_password):
    """
    Gets a new access token for ONE MAP

    :param one_map_email: Email account for ONE MAP
    :param one_map_password: Password for ONE MAP
    :return: token, datetime of expiry
    """
    url = "https://developers.onemap.sg/privateapi/auth/post/getToken"
    headers = {"Content-Type": "application/json"}
    params = {
        "email": one_map_email,
        "password": one_map_password
    }
    r = requests.post(url, headers=headers, data=json.dumps(params))
    pjson = r.json()
    token = pjson['access_token']
    expiry = datetime.fromtimestamp(pjson['expiry_timestamp'])

    return token, expiry


def search_one_map(query, page_num=0):
    """
    Given a search query, return the found locations, lat and long

    :param query: str, location to find
    :param page_num: Page number of queries
    :return: str Found location, int Latitude, int Longitude
    """

    url = "https://developers.onemap.sg/commonapi/search"
    params = {
        "searchVal": query,
        "returnGeom": "Y",
        "getAddrDetails": "Y",
        "pageNum": 1
    }
    r = requests.get(url, params=params)
    pjson = r.json()
    return pjson


def get_one_map_map(lat, long, points, layerchosen='default', zoom=17, width=512, height=512):
    """
    Given the params, create a map using One Map

    :param lat: Latitude of center of map
    :param long: Longitude of center of map
    :param points: Points to place pins
    :param layerchosen: Style of map
    :param zoom: Zoom of map
    :param width: Width of map
    :param height: Height of map
    :return: urllib3 object
    """
    url = 'https://developers.onemap.sg/commonapi/staticmap/getStaticImage'
    params = {
        "layerchosen": layerchosen,
        "lat": lat,
        "lng": long,
        "zoom": zoom,
        "width": width,
        "height": height,
        "points": points
    }

    r = requests.get(url, params=params, stream=True)
    return r.raw
