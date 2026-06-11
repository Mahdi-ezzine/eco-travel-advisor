"""
services.py

External service integrations and decision helpers used by the Rasa custom
actions.
"""

import requests

from config import get_secret

# Standard emission factors in kilograms of CO2 per passenger-kilometre,
# used as a fallback when the Climatiq API is unavailable.
EMISSION_FACTORS = {
    "train": 0.041,
    "bus": 0.027,
    "flight": 0.255,
    "ferry": 0.115,
    "car": 0.171,
}

CLIMATIQ_ACTIVITY = {
    "train": "passenger_train-route_type_national-fuel_source_na",
    "bus": "passenger_vehicle-vehicle_type_bus-fuel_source_na",
    "flight": "passenger_flight-route_type_international-aircraft_type_na",
    "ferry": "sea_travel-route_type_ferry-vehicle_type_na",
    "car": "passenger_vehicle-vehicle_type_car-fuel_source_na",
}

REQUEST_TIMEOUT = 6


def estimate_carbon(mode, distance_km, passengers=1):
    """
    Estimate trip carbon for a transport leg.

    Tries the Climatiq API when CLIMATIQ_API_KEY is set; on any error or when
    no key is present, falls back to standard emission factors. Returns a dict
    with the value and the source used.
    """
    distance_km = float(distance_km or 0)
    passengers = max(1, int(passengers or 1))
    key = get_secret("CLIMATIQ_API_KEY", "CLIMATIQ_KEY")

    if key:
        try:
            activity_id = CLIMATIQ_ACTIVITY.get(mode, CLIMATIQ_ACTIVITY["car"])
            response = requests.post(
                "https://api.climatiq.io/data/v1/estimate",
                headers={"Authorization": "Bearer {0}".format(key)},
                json={
                    "emission_factor": {
                        "activity_id": activity_id,
                        "data_version": "^6",
                    },
                    "parameters": {
                        "distance": distance_km,
                        "distance_unit": "km",
                        "passengers": passengers,
                    },
                },
                timeout=REQUEST_TIMEOUT,
            )
            if response.status_code == 200:
                value = float(response.json().get("co2e", 0))
                return {"carbon_kg": round(value, 2), "source": "climatiq"}
        except Exception:
            pass

    factor = EMISSION_FACTORS.get(mode, EMISSION_FACTORS["car"])
    value = distance_km * factor * passengers
    return {"carbon_kg": round(value, 2), "source": "fallback_factor"}


def geocode_city(city):
    """
    Resolve a city name to coordinates using OpenCage, if a key is configured.

    Returns a dict with lat and lng, or None when the service is unavailable.
    Optional and non-blocking.
    """
    key = get_secret("OPENCAGE_API_KEY", "OPENCAGE_KEY")
    if not key or not city:
        return None
    try:
        response = requests.get(
            "https://api.opencagedata.com/geocode/v1/json",
            params={"q": city, "key": key, "limit": 1},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            results = response.json().get("results", [])
            if results:
                geometry = results[0]["geometry"]
                components = results[0].get("components", {})
                return {
                    "lat": geometry["lat"],
                    "lng": geometry["lng"],
                    "country": components.get("country"),
                    "formatted": results[0].get("formatted"),
                }
    except Exception:
        pass
    return None


def route_distance_km(origin_city, destination_city, mode="driving-car"):
    """
    Estimate road distance between two cities using OpenRouteService, if keys
    for both OpenCage (geocoding) and ORS are configured. Returns kilometres or
    None. Optional and non-blocking.
    """
    ors_key = get_secret("ORS_API_KEY", "OPENROUTESERVICE_API_KEY")
    if not ors_key:
        return None
    origin = geocode_city(origin_city)
    destination = geocode_city(destination_city)
    if not origin or not destination:
        return None
    try:
        response = requests.post(
            "https://api.openrouteservice.org/v2/directions/{0}".format(mode),
            headers={"Authorization": ors_key},
            json={
                "coordinates": [
                    [origin["lng"], origin["lat"]],
                    [destination["lng"], destination["lat"]],
                ]
            },
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            summary = response.json()["routes"][0]["summary"]
            return round(summary["distance"] / 1000.0, 2)
    except Exception:
        pass
    return None


def carbon_band(carbon_kg, low_threshold=50, high_threshold=200):
    """
    Map a carbon figure (kg CO2) to a colour band for the UI result card.

    green  = low emission, amber = moderate, red = high.
    """
    carbon_kg = float(carbon_kg or 0)
    if carbon_kg <= low_threshold:
        return "green"
    if carbon_kg <= high_threshold:
        return "amber"
    return "red"


def _normalise(value, minimum, maximum):
    """Scale a value to the 0..1 range; returns 0 when the range is degenerate."""
    if maximum <= minimum:
        return 0.0
    return (float(value) - minimum) / (maximum - minimum)


# Weighting profiles by sustainability preference level. Each profile gives the
# relative importance of low carbon, low price, and the intrinsic eco quality
# of the option. They sum to 1.
WEIGHT_PROFILES = {
    "low": {"carbon": 0.2, "price": 0.6, "eco": 0.2},
    "medium": {"carbon": 0.45, "price": 0.35, "eco": 0.2},
    "high": {"carbon": 0.65, "price": 0.15, "eco": 0.2},
}


def score_options(options, carbon_key, price_key, eco_key=None,
                  sustainability_level="medium"):
    """
    Rank candidate options with a weighted scoring function that combines
    carbon impact, price, and an intrinsic eco-quality field, according to the
    user's sustainability preference. Lower carbon and price score higher.

    options: list of dicts. Returns the same list sorted best-first, each with
    an added "eco_score" between 0 and 100.
    """
    if not options:
        return []
    weights = WEIGHT_PROFILES.get(sustainability_level, WEIGHT_PROFILES["medium"])

    carbons = [float(option.get(carbon_key) or 0) for option in options]
    prices = [float(option.get(price_key) or 0) for option in options]
    c_min, c_max = min(carbons), max(carbons)
    p_min, p_max = min(prices), max(prices)

    if eco_key:
        ecos = [float(option.get(eco_key) or 0) for option in options]
        e_min, e_max = min(ecos), max(ecos)
    else:
        e_min, e_max = 0.0, 1.0

    for option in options:
        carbon_component = 1.0 - _normalise(option.get(carbon_key) or 0, c_min, c_max)
        price_component = 1.0 - _normalise(option.get(price_key) or 0, p_min, p_max)
        if eco_key:
            eco_component = _normalise(option.get(eco_key) or 0, e_min, e_max)
        else:
            eco_component = 0.5
        score = (
            weights["carbon"] * carbon_component
            + weights["price"] * price_component
            + weights["eco"] * eco_component
        )
        option["eco_score"] = round(score * 100, 1)

    return sorted(options, key=lambda item: item["eco_score"], reverse=True)
