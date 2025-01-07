from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from streamlit_tree_select import tree_select

import wizzair as wz

pd.options.mode.copy_on_write = True

st.title("Flight Deals Finder")
st.text("Find destinations with the best flight deals from your location.")
st.markdown("*Only WizzAir flights are supported at the moment.*")
st.divider()

invalid_data = False

today = pd.to_datetime("today").date()
last_day = pd.to_datetime("today").date() + timedelta(days=42)
date_range: tuple[date, date] = st.date_input(
    "Date range for search (earliest and latest date for departure):",
    [today, last_day],  # type: ignore
    min_value=today,
)

if len(date_range) != 2:
    invalid_data = True
    st.error("Please select a start and and end date.")
elif (date_range[1] - date_range[0]).days > 42:
    st.error("Date range cannot be longer than 42 days.")
    invalid_data = True
elif (date_range[1] - date_range[0]).days < 0:
    st.error("End date cannot be before start date.")
    invalid_data = True

airports = wz.fetch_airports()


def format_airport(iata, country_code=True):
    postfix = f" ({airports[iata]['countryCode']})" if country_code else ""
    return f"{iata} - {airports[iata]['shortName']}" + postfix


start_place = st.selectbox(
    "Flying from:",
    sorted(airports),
    index=None,
    placeholder="Select airport...",
    format_func=format_airport,
)

dest_country_airports = defaultdict(list)
if start_place:
    currency = airports[start_place]["currencyCode"]
    for iata in airports[start_place]["connections"]:
        if not airports[iata]["isFakeStation"]:
            dest_country_airports[airports[iata]["countryName"]].append(iata)

nodes = [
    {
        "label": "All",
        "value": "all",
        "children": [
            {
                "label": country,
                "value": country,
                "children": [
                    {"label": format_airport(iata, False), "value": iata}
                    for iata in airports
                ],
            }
            for country, airports in sorted(dest_country_airports.items())
        ],
    },
]

st.text("Flying to:")
destinations = list[str]()
if start_place:
    destinations = tree_select(
        nodes, check_model="leaf", expand_on_click=True, expanded=["all"]
    )["checked"]
    st.write(len(destinations), "destinations selected")
else:
    st.warning("Please select a starting airport first.")

two_way = st.toggle("Return flight", True)
min_nights, max_nights = st.slider(
    "Min/max nights before returning:", 0, 41, (1, 2), disabled=not two_way
)
if len(date_range) == 2 and min_nights > (date_range[1] - date_range[0]).days:
    st.error("Min nights cannot be larger than the length of the date range.")
    invalid_data = True

if not st.button("Search", type="primary"):
    st.stop()

if not start_place:
    invalid_data = True
    st.error("Please select a starting airport.")
if not destinations:
    invalid_data = True
    st.error("Please select at least one destination.")
if invalid_data:
    st.stop()

progr_text = "Finding best fares..."
progr = st.progress(0, progr_text)
best_flights = []
for i, destination in enumerate(destinations):
    flights_df = wz.find_flights(
        start_place, destination, *date_range, two_way, min_nights, max_nights
    )
    progr.progress((i + 1) / len(destinations), progr_text)
    if not flights_df.empty:
        min_price_flight = flights_df.loc[flights_df["Price"].idxmin()]
        min_price_flight["Destination"] = destination
        best_flights.append(min_price_flight)
progr.empty()

best, *details = st.tabs(["Best"] + destinations)

with best:
    best.subheader("Best flights to all destinations")
    if best_flights:
        best_flights_df = pd.DataFrame(best_flights)
        best_flights_df.sort_values(by="Price", inplace=True, ignore_index=True)
        if best_flights_df["Return from"].equals(best_flights_df["Destination"]):
            best_flights_df.drop(columns=["Return from"], inplace=True)
        columns = best_flights_df.columns.tolist()
        columns.remove("Destination")
        columns.insert(1, "Destination")
        st.dataframe(
            best_flights_df.style.format({"Price": "{:,g} " + currency}, precision=2),
            use_container_width=True,
            column_order=columns,
            column_config={
                "Departure Time": st.column_config.DatetimeColumn(),
                "Departure Time (Outbound)": st.column_config.DatetimeColumn(),
                "Departure Time (Return)": st.column_config.DatetimeColumn(),
                "Book": st.column_config.LinkColumn(display_text=r"https://([^/]*)/.*"),
            },
        )
    else:
        st.write("No flights found with the selected parameters.")

for i in range(len(details)):
    with details[i]:
        details[i].subheader(f"Flights to {format_airport(destinations[i])}")
        flights_df = wz.find_flights(
            start_place, destinations[i], *date_range, two_way, min_nights, max_nights
        )
        if flights_df.empty:
            details[i].write(
                "No flights found for this destination with the selected parameters."
            )
            continue
        if flights_df["Return from"].eq(destinations[i]).all():
            flights_df.drop(columns=["Return from"], inplace=True)
        st.dataframe(
            flights_df.style.format({"Price": "{:,g} " + currency}, precision=2),
            use_container_width=True,
            column_config={
                "Departure Time": st.column_config.DatetimeColumn(),
                "Departure Time (Outbound)": st.column_config.DatetimeColumn(),
                "Departure Time (Return)": st.column_config.DatetimeColumn(),
                "Book": st.column_config.LinkColumn(display_text=r"https://([^/]*)/.*"),
            },
        )
