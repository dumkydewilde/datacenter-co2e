import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import geopy.distance
import os

# data prep
df = pd.read_json("poc/instance_data.json")
df["lat"] = df["geo"].apply(lambda x: x["latitude"])
df["lon"] = df["geo"].apply(lambda x: x["longitude"])
df['co2e'] = df["emission_details"].apply(lambda x: x["co2e"])

df_grouped = df.groupby(by=["dc_cq_id", "lat", "lon"])["co2e"].mean().reset_index()

# distances
distance_lookup = {}
for index, row in df_grouped.iterrows():
    distance_lookup[row["dc_cq_id"]] = {
            dest["dc_cq_id"] : 
            geopy.distance.geodesic((dest["lat"],dest["lon"]), (row["lat"], row["lon"])).km 
            for i, dest in df_grouped.iterrows() if row["dc_cq_id"] != dest["dc_cq_id"]
        }

def calculate_latency_distance(latency_ms, path_adjustement_pct=0.1, equipment_latency_ms=1):
    fibre_speed = 200 #km/ms
    rountrip_factor = 2
    kms = (latency_ms  - equipment_latency_ms) / 2 * fibre_speed
    adjusted_kms = kms / (1 + path_adjustement_pct) 

    return round(adjusted_kms)

def calculate_latency(km, path_adjustement_pct=0.1, equipment_latency_ms=1):
    fibre_speed = 200 #km/ms
    rountrip_factor = 2

    kms = km * (1 + path_adjustement_pct) * rountrip_factor
    latency  = kms / fibre_speed + equipment_latency_ms

    return round(latency,2)

def get_co2_equivalent(co2_kg, type="car_kilometers"):
    if type == "car_kilometers":
        # Equivalent KMs for Toyota Corolla 2020 (i.e. most popular car in the world)
        factor = 0.196974607

    return f"{round(co2_kg * factor, 2)} km"

"""
# Data Center CO2 Emissions
Compare data centers on CO2 emissions (cpu, RAM, storage, networking). Currently only Azure and cpu. Compares on the avg. CO2 emissions per cpu core of selected VM instance types.
"""

l1, r1 = st.columns(2)
with l1:
    provider = st.selectbox(
    'Current provider',
    ["aws", "azure", "gcp"],
    1)

    activity_type = st.selectbox(
        'Type',
        df["activity_type"].unique())

    latency = st.slider('Acceptable latency', 0, 200, 50)


with r1:
    current_dc = st.selectbox(
    'Current data center',
    df["dc_cq_id"].unique(),
    list(df["dc_cq_id"].unique()).index("west_europe"))

    activity_sub_type = st.multiselect(
        'VM instance type',
        df["activity_sub_type"].unique())

    st.write('Latency range (estimated):', f"{calculate_latency_distance(latency)} KM")


if len(activity_sub_type) > 0:
    filtered_data = df[df["activity_sub_type"].isin(activity_sub_type)]
else: 
    filtered_data = df

options_in_range = [k for k,v in distance_lookup[current_dc].items() if v < calculate_latency_distance(latency)]

if len(options_in_range) > 0:
    current_emissions = filtered_data[filtered_data["dc_cq_id"] == current_dc].groupby(by=["dc_cq_id"])["co2e"].mean()[0]
    best_options_df = filtered_data[filtered_data["dc_cq_id"].isin(options_in_range)].groupby(by=["dc_cq_id"])["co2e"].mean().sort_values().reset_index()
    best_options_df["co2e_delta"] = current_emissions - best_options_df["co2e"]
    best_options_df["latency"] = best_options_df["dc_cq_id"].apply(lambda x: calculate_latency(distance_lookup[current_dc][x]))
    best_options_df = best_options_df[best_options_df["co2e_delta"] > 0]

    if len(best_options_df) > 0:
        best_co2e_delta = best_options_df["co2e_delta"][0]

        best_alternative_name = best_options_df['dc_cq_id'][0]

        latency_co2e_fig = px.scatter(
            best_options_df, 
            title="Best alternatives",
            x="latency", 
            y="co2e", 
            color="co2e_delta", 
            color_continuous_scale = "RdYlGn",
            hover_name="dc_cq_id"
            )

        st.plotly_chart(latency_co2e_fig)
    else:
        st.write("No better alternatives in range, increase latency to find alternatives.")
        best_alternative_name = "(No better alternative in range)"
        best_co2e_delta = 0

else:
    st.write("No alternatives in range, increase latency to find alternatives.")
    best_alternative_name = "(No alternative in range)"
    best_co2e_delta = 0

st.write("## Potential Savings")
st.write(f"Moving to datacenter: {best_alternative_name}")
l2, r2 = st.columns(2)
with l2:
    num_inst = st.number_input("Number of instances", value=1, min_value=1)
    num_cpus = st.number_input("Number of cpus", value=4, min_value=1, max_value=1024)

with r2:
    day_hours = st.number_input("Hours on per day", value=4, min_value=1, max_value=24)
    days_week = st.number_input("Days per week", value=7, min_value=1, max_value=7)


with l2:
    current_co2e_year = (days_week/7)*day_hours*365*num_inst*num_cpus*current_emissions
    st.metric("Current yearly emissions (kg CO2)", f"{round(current_co2e_year, 2)}")
    st.metric("Car KM equivalent (current)", f"{get_co2_equivalent(current_co2e_year)}")
with r2:
    savings_year = (days_week/7)*day_hours*365*num_inst*num_cpus*best_co2e_delta
    st.metric("Potential yearly savings (kg CO2)", f"{round(savings_year, 2)}")
    st.metric("Car KM (saved)", f"{get_co2_equivalent(savings_year)}")



st.write("## Overview of datacenters globally")


fig = px.scatter_geo(filtered_data, 
                lat="lat",
                lon="lon",
                color="co2e",
                hover_name="dc_cq_id", 
                projection="natural earth",
                color_continuous_scale = "RdYlGn_r",
                template="plotly",
                width=1000
                )

st.plotly_chart(fig, use_container_width=True)