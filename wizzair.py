from datetime import timedelta
from time import sleep

import pandas as pd
import requests
import streamlit as st

# TODO dynamically update version from website
API_URL = "https://be.wizzair.com/26.4.0/Api/"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "authority": "be.wizzair.com",
    "content-type": "application/json;charset=UTF-8",
    "origin": "https://wizzair.com",
    "referer": "https://wizzair.com/en-gb/flights/timetable",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


@st.cache_data(ttl=timedelta(days=1), show_spinner=False)
def fetch_airports():
    response = requests.get(
        API_URL + "asset/map", params={"languageCode": "en-gb"}, headers=HEADERS
    )
    response.raise_for_status()
    cities = response.json()["cities"]
    for city in cities:
        city["connections"] = sorted(c["iata"] for c in city["connections"])
        city["shortName"] = city["shortName"].strip()
    airports = {city["iata"]: city for city in cities}
    return airports


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_timetable(departure, destination, date_from, date_to):
    payload = {
        "flightList": [
            {
                "departureStation": departure,
                "arrivalStation": destination,
                "from": date_from.strftime("%Y-%m-%d"),
                "to": date_to.strftime("%Y-%m-%d"),
            },
            {
                "departureStation": destination,
                "arrivalStation": departure,
                "from": date_from.strftime("%Y-%m-%d"),
                "to": date_to.strftime("%Y-%m-%d"),
            },
        ],
        "priceType": "regular",
        "adultCount": 1,
        "childCount": 0,
        "infantCount": 0,
    }
    response = requests.post(
        API_URL + "search/timetable", json=payload, headers=HEADERS
    )
    response.raise_for_status()
    timetable = response.json()
    outbound = pd.DataFrame(timetable["outboundFlights"])
    returns = pd.DataFrame(timetable["returnFlights"])
    for df in [outbound, returns]:
        if df.empty:
            continue
        df.drop(columns=["originalPrice", "priceType", "hasMacFlight"], inplace=True)
        df["departureDate"] = pd.to_datetime(df["departureDate"])
        df["price"] = [x["amount"] for x in df["price"]]
        df.drop(df[df["price"] == 0].index, inplace=True)
        # df.round({"price": 2})
    sleep(0.25)
    return outbound, returns


@st.cache_data(ttl=3600, show_spinner=False)
def find_flights(
    departure, destination, date_from, date_to, two_way, min_nights=0, max_nights=42
):
    try:
        outbound, returns = _fetch_timetable(departure, destination, date_from, date_to)
    except Exception as e:
        return pd.DataFrame()
    if two_way:
        trips = []
        for i, out in outbound.iterrows():
            for j, ret in returns.iterrows():
                if (
                    timedelta(days=min_nights)
                    <= ret["departureDate"] - out["departureDate"]
                    <= timedelta(days=max_nights)
                ):
                    trips.append(
                        {
                            "Price": out["price"] + ret["price"],
                            "Departure (Outbound)": pd.to_datetime(
                                out["departureDates"][0]
                            ),
                            "Return from": ret["departureStation"],
                            "Departure (Return)": pd.to_datetime(
                                ret["departureDates"][-1]
                            ),
                            "Book": f"https://wizzair.com/en-gb/booking/select-flight/{departure}/{destination}/{out['departureDates'][0].split("T")[0]}/{ret['departureDates'][-1].split("T")[0]}/1/0/0",
                        }
                    )
        flights = pd.DataFrame(trips)
    else:
        flights = pd.DataFrame(
            [
                {
                    "Price": out["price"],
                    "Departure": pd.to_datetime(out["departureDates"][0]),
                    "Book": f"https://wizzair.com/en-gb/booking/select-flight/{departure}/{destination}/{out['departureDates'][0].split("T")[0]}/null/1/0/0",
                }
                for i, out in outbound.iterrows()
            ]
        )
    if not flights.empty:
        flights.sort_values(by="Price", inplace=True, ignore_index=True)
    return flights[:200]
