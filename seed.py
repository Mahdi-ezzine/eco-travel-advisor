"""
seed.py

Populate Neon with realistic synthetic data using Faker.

Performance: every table is inserted with a single batched statement
(psycopg2.extras.execute_values) instead of one round-trip per row. Against a
remote database such as Neon this is dramatically faster than row-by-row
inserts.

Coverage: transport options are generated for every ordered pair of catalogue
cities, and every city receives hotels and cultural experiences, so the
assistant always finds data for any known city.

Volumes are modest and configurable at the top of this file.
"""

import random
import datetime

from faker import Faker
from psycopg2.extras import Json, execute_values

from db import create_connection

fake = Faker()

# --- Configurable volumes -------------------------------------------------
HOTELS_PER_CITY = 8          # 30 cities -> 240 hotels
# Transport: train and bus on every pair, ferry only between coastal cities,
# plus one random extra mode -> roughly 2800 transport options (full coverage).
NUM_OFFSETS = 60
EXPERIENCES_PER_CITY = 5     # 30 cities -> 150 experiences
NUM_SESSIONS = 120
AVG_MESSAGES = 6

CITIES = [
    "Paris", "Berlin", "Madrid", "Rome", "Amsterdam", "Lisbon", "Vienna",
    "Prague", "Copenhagen", "Stockholm", "Oslo", "Helsinki", "Zurich",
    "Brussels", "Dublin", "Barcelona", "Munich", "Milan", "Athens", "Warsaw",
    "Budapest", "London", "Edinburgh", "Porto", "Valencia", "Nice", "Geneva",
    "Hamburg", "Krakow", "Ljubljana",
]

COUNTRY_BY_CITY = {
    "Paris": "France", "Nice": "France", "Berlin": "Germany",
    "Munich": "Germany", "Hamburg": "Germany", "Madrid": "Spain",
    "Barcelona": "Spain", "Valencia": "Spain", "Rome": "Italy",
    "Milan": "Italy", "Amsterdam": "Netherlands", "Lisbon": "Portugal",
    "Porto": "Portugal", "Vienna": "Austria", "Prague": "Czechia",
    "Copenhagen": "Denmark", "Stockholm": "Sweden", "Oslo": "Norway",
    "Helsinki": "Finland", "Zurich": "Switzerland", "Geneva": "Switzerland",
    "Brussels": "Belgium", "Dublin": "Ireland", "Edinburgh": "United Kingdom",
    "London": "United Kingdom", "Athens": "Greece", "Warsaw": "Poland",
    "Krakow": "Poland", "Budapest": "Hungary", "Ljubljana": "Slovenia",
}

ECO_CERTIFICATIONS = [
    "Green Key", "EU Ecolabel", "Green Globe", "EarthCheck",
    "Travelife Gold", "Biosphere Responsible Tourism", "LEED Certified",
]

TRANSPORT_MODES = ["train", "bus", "flight", "ferry", "car"]

# Cities with a coast or major port: ferry routes are only generated between
# two of these, so the ferry never appears for purely inland pairs.
COASTAL_CITIES = {
    "Amsterdam", "Lisbon", "Porto", "Barcelona", "Valencia", "Nice", "Dublin",
    "Edinburgh", "London", "Athens", "Copenhagen", "Stockholm", "Oslo",
    "Helsinki", "Hamburg",
}

# Kilograms of CO2 per passenger-kilometre.
EMISSION_FACTORS = {
    "train": 0.041, "bus": 0.027, "flight": 0.255, "ferry": 0.115, "car": 0.171,
}

# Average speed in km/h, used to derive a plausible duration.
AVERAGE_SPEED = {
    "train": 120, "bus": 80, "flight": 700, "ferry": 40, "car": 90,
}

OFFSET_PROJECT_TYPES = [
    "Reforestation", "Renewable energy", "Methane capture",
    "Clean cookstoves", "Peatland restoration", "Blue carbon",
]

CULTURAL_CATEGORIES = [
    "Guided heritage walk", "Local cooking class", "Artisan workshop",
    "Community farm visit", "Traditional music evening", "Museum tour",
    "Cycling tour", "Nature reserve hike",
]

INTENTS = [
    "greet", "plan_trip", "provide_destination", "provide_dates",
    "provide_budget", "provide_sustainability_level", "ask_carbon_footprint",
    "ask_accommodation", "ask_transport", "ask_offset", "ask_cultural",
    "request_human", "goodbye",
]


def _country(city):
    return COUNTRY_BY_CITY.get(city, fake.country())


def _batch_insert(sql, rows, fetch=False, page_size=200):
    """Insert a list of tuples in one batched statement."""
    conn = create_connection()
    if not conn:
        print("Connection failed.")
        return [] if fetch else None
    cur = conn.cursor()
    try:
        result = execute_values(cur, sql, rows, fetch=fetch, page_size=page_size)
        conn.commit()
        return result if fetch else None
    except Exception as error:
        conn.rollback()
        print("Batch insert error: {0}".format(error))
        return [] if fetch else None
    finally:
        cur.close()
        conn.close()


def seed_hotels(per_city=HOTELS_PER_CITY):
    rows = []
    for city in CITIES:
        for _ in range(per_city):
            score = random.randint(40, 100)
            carbon = max(0.5, round(random.uniform(2, 30) * (1.2 - score / 100.0), 2))
            rows.append((
                "{0} {1}".format(fake.last_name(), random.choice(
                    ["Eco Lodge", "Green Hotel", "Sustainable Stay",
                     "Boutique Eco", "Nature Resort", "Eco Inn"])),
                city, _country(city), random.choice(ECO_CERTIFICATIONS),
                round(random.uniform(45, 380), 2), score, carbon,
                random.randint(0, 40),
            ))
    _batch_insert(
        "INSERT INTO EcoHotel (name, city, country, eco_certification, "
        "price_per_night, sustainability_score, carbon_per_night_kg, "
        "rooms_available) VALUES %s", rows)
    print("Seeded {0} eco hotels.".format(len(rows)))


def seed_transport(extra_random_modes=1):
    """Generate transport options for every ordered city pair.

    Train and bus are always present (the lowest-carbon modes), a ferry is
    added only between two coastal cities, and one further mode (flight or car)
    is added at random. All modes of a given pair share the same distance, so
    comparing their carbon is meaningful and the greenest option is realistic.
    """
    rows = []
    for origin in CITIES:
        for destination in CITIES:
            if origin == destination:
                continue
            distance = round(random.uniform(150, 2200), 2)
            modes = ["train", "bus"]
            if origin in COASTAL_CITIES and destination in COASTAL_CITIES:
                modes.append("ferry")
            extras = [m for m in ["flight", "car"] if m not in modes]
            random.shuffle(extras)
            modes.extend(extras[:max(0, extra_random_modes)])
            for mode in modes:
                carbon = round(distance * EMISSION_FACTORS[mode], 2)
                duration = int((distance / AVERAGE_SPEED[mode]) * 60)
                departure = fake.date_time_between(start_date="+1d",
                                                   end_date="+60d")
                arrival = departure + datetime.timedelta(minutes=duration)
                price = distance * random.uniform(0.05, 0.35)
                if mode == "flight":
                    price *= 1.5
                rows.append((
                    origin, destination, mode,
                    "{0} {1}".format(fake.company().split()[0], mode.title()),
                    round(price, 2), duration, distance, carbon,
                    departure, arrival,
                ))
    _batch_insert(
        "INSERT INTO TransportOption (origin_city, destination_city, mode, "
        "provider, price, duration_minutes, distance_km, carbon_kg, "
        "departure_time, arrival_time) VALUES %s", rows)
    print("Seeded {0} transport options.".format(len(rows)))


def seed_offsets(n=NUM_OFFSETS):
    rows = []
    for _ in range(n):
        rows.append((
            "{0} {1} Project".format(
                random.choice(OFFSET_PROJECT_TYPES).split()[0], fake.city()),
            fake.company(), _country(random.choice(CITIES)),
            round(random.uniform(5, 45), 2),
            random.choice(OFFSET_PROJECT_TYPES),
            random.random() < 0.7, fake.sentence(nb_words=14),
        ))
    _batch_insert(
        "INSERT INTO CarbonOffsetProgram (name, provider, country, "
        "price_per_ton, project_type, verified, description) VALUES %s", rows)
    print("Seeded {0} carbon offset programs.".format(len(rows)))


def seed_experiences(per_city=EXPERIENCES_PER_CITY):
    rows = []
    for city in CITIES:
        for _ in range(per_city):
            category = random.choice(CULTURAL_CATEGORIES)
            rows.append((
                "{0} in {1}".format(category, city), city, _country(city),
                category, round(random.uniform(0, 120), 2),
                random.random() < 0.6, round(random.uniform(1, 8), 1),
                fake.sentence(nb_words=12),
            ))
    _batch_insert(
        "INSERT INTO CulturalExperience (name, city, country, category, price, "
        "supports_local_community, duration_hours, description) VALUES %s", rows)
    print("Seeded {0} cultural experiences.".format(len(rows)))


def seed_faq():
    conn = create_connection()
    if not conn:
        return
    cur = conn.cursor()
    faq_items = [
        ("How do you calculate the carbon footprint of a trip?",
         "We estimate emissions from distance and transport mode using the "
         "Climatiq API, falling back to standard emission factors when needed.",
         "carbon"),
        ("What does an eco-certification like Green Key mean?",
         "It is an independent label awarded to accommodations that meet strict "
         "environmental and social criteria.",
         "accommodation"),
        ("Which transport mode is the most sustainable?",
         "For most routes, trains and buses produce far less carbon per "
         "passenger-kilometre than flights or private cars.",
         "transport"),
        ("How do carbon offset programs work?",
         "They fund projects such as reforestation or renewable energy that "
         "remove or avoid an equivalent amount of greenhouse gas emissions.",
         "offset"),
        ("Can I talk to a human travel advisor?",
         "Yes. At any point you can ask to speak with a human advisor and we "
         "will pass on your full trip context.",
         "support"),
        ("How is my personal data handled?",
         "We store only what is needed to plan your trip and process it in line "
         "with GDPR. You can request deletion at any time.",
         "privacy"),
        ("What is a sustainability preference level?",
         "It tells the assistant how strongly to prioritise low-carbon and "
         "community-supporting options over price and speed.",
         "general"),
        ("Do you support local communities?",
         "Many recommended cultural experiences are run by local operators and "
         "are flagged as supporting the local community.",
         "cultural"),
        ("Are the carbon figures exact?",
         "They are approximate estimates intended to guide decisions, not "
         "certified measurements.",
         "carbon"),
        ("Can the assistant plan a multi-city trip?",
         "It focuses on a single origin and destination per plan, but you can "
         "create several plans for a multi-city itinerary.",
         "general"),
        ("What budget information do you need?",
         "An approximate total budget helps rank options that fit your trip "
         "without exceeding your spending limit.",
         "general"),
        ("How accurate is automatic location detection?",
         "When enabled, we geocode the city name you provide; we do not track "
         "your device location.",
         "privacy"),
    ]
    try:
        execute_values(
            cur,
            "INSERT INTO EcoFAQ (question, answer, category) VALUES %s "
            "ON CONFLICT (question) DO NOTHING",
            faq_items)
        conn.commit()
        print("Seeded {0} FAQ entries.".format(len(faq_items)))
    except Exception as error:
        conn.rollback()
        print("Error seeding FAQ: {0}".format(error))
    finally:
        cur.close()
        conn.close()


def seed_conversations(num_sessions=NUM_SESSIONS, avg_messages=AVG_MESSAGES):
    """Seed chat sessions, messages, trip plans and items in batched inserts."""
    conn = create_connection()
    if not conn:
        return
    cur = conn.cursor()
    try:
        cur.execute("SELECT hotel_id, carbon_per_night_kg, price_per_night "
                    "FROM EcoHotel LIMIT 200;")
        hotels = cur.fetchall()
        cur.execute("SELECT transport_id, carbon_kg, price, origin_city, "
                    "destination_city FROM TransportOption LIMIT 400;")
        transports = cur.fetchall()

        # Sessions (batched, returning ids).
        session_rows = []
        for _ in range(num_sessions):
            started = fake.date_time_between(start_date="-1y", end_date="now")
            ended = started + datetime.timedelta(minutes=random.randint(2, 30))
            session_rows.append((fake.uuid4(), started, ended))
        sessions = execute_values(
            cur,
            "INSERT INTO ChatSession (user_ref, started_at, ended_at) "
            "VALUES %s RETURNING session_id, started_at",
            session_rows, fetch=True)

        # Messages (batched).
        message_rows = []
        for session_id, started in sessions:
            num_messages = max(2, int(random.gauss(avg_messages, 2)))
            for turn in range(num_messages):
                sender = "user" if turn % 2 == 0 else "bot"
                intent = random.choice(INTENTS) if sender == "user" else None
                entities = {}
                if intent in ("provide_destination", "plan_trip"):
                    entities = {"destination": random.choice(CITIES)}
                message_rows.append((
                    session_id, sender, fake.sentence(nb_words=8), intent,
                    Json(entities),
                    started + datetime.timedelta(seconds=turn * 20)))
        if message_rows:
            execute_values(
                cur,
                "INSERT INTO ChatMessage (session_id, sender, text, intent, "
                "entities, created_at) VALUES %s", message_rows, page_size=300)

        # Trip plans for ~80 percent of sessions (batched, returning ids).
        plan_rows, plan_meta = [], []
        if transports:
            for session_id, started in sessions:
                if random.random() < 0.8:
                    origin, destination = random.sample(CITIES, 2)
                    start_date = fake.date_between(start_date="-1y",
                                                   end_date="+60d")
                    end_date = start_date + datetime.timedelta(
                        days=random.randint(2, 14))
                    level = random.choice(["low", "medium", "high"])
                    hotel = random.choice(hotels) if hotels else None
                    transport = random.choice(transports)
                    nights = (end_date - start_date).days
                    total = float(transport[1] or 0)
                    if hotel:
                        total += float(hotel[1] or 0) * nights
                    plan_rows.append((
                        session_id, origin, destination, start_date, end_date,
                        round(random.uniform(300, 4000), 2), level,
                        round(total, 2), "confirmed", started))
                    plan_meta.append((hotel, transport, nights))

        plans = []
        if plan_rows:
            plans = execute_values(
                cur,
                "INSERT INTO TripPlan (session_id, origin, destination, "
                "start_date, end_date, budget, sustainability_level, "
                "total_carbon_kg, status, created_at) VALUES %s "
                "RETURNING plan_id", plan_rows, fetch=True)

        # Plan items (batched).
        item_rows = []
        for plan_row, (hotel, transport, nights) in zip(plans, plan_meta):
            plan_id = plan_row[0]
            item_rows.append((
                plan_id, "transport", transport[0],
                "{0} to {1}".format(transport[3], transport[4]),
                transport[2], transport[1]))
            if hotel:
                item_rows.append((
                    plan_id, "hotel", hotel[0], "Eco hotel stay", hotel[2],
                    round(float(hotel[1] or 0) * nights, 2)))
        if item_rows:
            execute_values(
                cur,
                "INSERT INTO TripPlanItem (plan_id, item_type, ref_id, "
                "description, price, carbon_kg) VALUES %s", item_rows,
                page_size=300)

        conn.commit()
        print("Seeded {0} chat sessions with messages and trip plans.".format(
            num_sessions))
    except Exception as error:
        conn.rollback()
        print("Error seeding conversations: {0}".format(error))
    finally:
        cur.close()
        conn.close()


def seed_all():
    """Seed the entire database with batched inserts (fast)."""
    seed_hotels()
    seed_transport()
    seed_offsets()
    seed_experiences()
    seed_faq()
    seed_conversations()
    print("Seeding complete.")


if __name__ == "__main__":
    seed_all()
