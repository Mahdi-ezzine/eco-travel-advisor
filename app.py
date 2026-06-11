"""
app.py

Streamlit frontend for the Eco-Travel Advisor.

"""

import uuid
from datetime import date, timedelta

import requests
import streamlit as st
import matplotlib.pyplot as plt

import analytics
from config import RASA_API_URL
from db import get_or_create_session, log_message

st.set_page_config(page_title="Eco-Travel Advisor", layout="wide")

st.markdown(
    """
    <style>
      h1, h2, h3 { color: #1b5e20; }
      .stButton>button {
          border-radius: 8px;
          border: 1px solid #2e7d32;
          background-color: #ffffff;
          color: #1b5e20;
          font-weight: 600;
      }
      .eco-card {
          border-radius: 10px;
          padding: 14px 16px;
          margin-bottom: 10px;
          border-left: 6px solid #9e9e9e;
          background-color: #f6f9f4;
          color: #1a1a1a;
      }
      .eco-card.green { border-left-color: #2e7d32; }
      .eco-card.amber { border-left-color: #f9a825; }
      .eco-card.red   { border-left-color: #c62828; }
      .eco-band {
          display: inline-block;
          padding: 2px 10px;
          border-radius: 12px;
          font-size: 12px;
          font-weight: 700;
          color: white;
      }
      .eco-band.green { background-color: #2e7d32; }
      .eco-band.amber { background-color: #f9a825; color: #1a1a1a; }
      .eco-band.red   { background-color: #c62828; }
      .handover-banner {
          background-color: #fff3e0;
          border: 1px solid #f9a825;
          border-radius: 10px;
          padding: 12px 16px;
          color: #e65100;
          font-weight: 700;
          margin: 10px 0;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

BAND_LABEL = {"green": "Low emission", "amber": "Moderate", "red": "High emission"}
BAND_TOOLTIP = {
    "green": "Low emission: a strong sustainable choice.",
    "amber": "Moderate emission: acceptable, but not the greenest option.",
    "red": "High emission: consider a lower-carbon alternative.",
}


@st.cache_data(ttl=60, show_spinner=False)
def cached_query(name):
    """Run a named analytics function and cache the result for 60 seconds.

    Streamlit re-runs the whole script on every interaction (including page
    switches). Without caching, each dashboard render opens several separate
    remote Neon connections, which is slow. Caching makes repeat renders and
    page switches instant.
    """
    return getattr(analytics, name)()


@st.cache_data(ttl=60, show_spinner=False)
def cached_sql(sql, params=None):
    """Cache an arbitrary read query (used by the Trip history page)."""
    return analytics._read(sql, params)


def init_session():
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "db_session" not in st.session_state:
        st.session_state.db_session = get_or_create_session(
            st.session_state.user_id)


def send_to_rasa(message):
    """Send a message to the Rasa REST channel and return the list of replies."""
    try:
        response = requests.post(
            RASA_API_URL,
            json={"sender": st.session_state.user_id, "message": message},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception as error:
        return [{"text": "Connection error: {0}".format(error)}]


def render_recommendation(custom):
    category = custom.get("category", "options")
    st.markdown("**Recommended {0}**".format(category))
    items = custom.get("items", [])
    if not items:
        return
    # Horizontal, carousel-style layout: one card per column.
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        band = item.get("band", "green")
        price = item.get("price")
        unit = item.get("unit", "")
        carbon = item.get("carbon_kg")
        eco_score = item.get("eco_score")
        details = []
        if price is not None:
            details.append("{0:.0f} euros {1}".format(price, unit).strip())
        if carbon is not None:
            details.append("{0:.1f} kg CO2".format(carbon))
        if eco_score is not None:
            details.append("eco score {0}/100".format(eco_score))
        col.markdown(
            "<div class='eco-card {band}' title='{tip}'>"
            "<span class='eco-band {band}' title='{tip}'>{label}</span> "
            "<strong>{title}</strong><br>{subtitle}<br>{details}</div>".format(
                band=band, tip=BAND_TOOLTIP.get(band, ""),
                label=BAND_LABEL.get(band, ""),
                title=item.get("title", ""),
                subtitle=item.get("subtitle", ""),
                details=" | ".join(details)),
            unsafe_allow_html=True,
        )


def render_carbon_summary(custom):
    band = custom.get("band", "green")
    distance = custom.get("distance_km")
    distance_source = custom.get("distance_source", "database")
    extra = ""
    if distance is not None:
        source_label = ("road route via OpenRouteService"
                        if distance_source == "openrouteservice"
                        else "catalogue distance")
        extra = "<br>Distance: {0:.0f} km ({1})".format(distance, source_label)
    st.markdown(
        "<div class='eco-card {band}' title='{tip}'>"
        "<span class='eco-band {band}' title='{tip}'>{label}</span> "
        "<strong>Estimated trip footprint: {total:.1f} kg CO2</strong><br>"
        "Greenest mode: {mode} | emission source: {source}{extra}</div>".format(
            band=band, tip=BAND_TOOLTIP.get(band, ""),
            label=BAND_LABEL.get(band, ""),
            total=float(custom.get("total_kg", 0)),
            mode=custom.get("mode", ""), source=custom.get("source", ""),
            extra=extra),
        unsafe_allow_html=True,
    )


def render_handover(custom):
    st.markdown(
        "<div class='handover-banner'>This conversation has been escalated to "
        "a human travel advisor (request {0}).</div>".format(
            custom.get("handover_id", "pending")),
        unsafe_allow_html=True,
    )


def render_handover_summary(custom):
    items = custom.get("items", {})
    if not items:
        return
    rows = "".join(
        "<li><strong>{0}:</strong> {1}</li>".format(k, v)
        for k, v in items.items())
    st.markdown(
        "<div class='eco-card'><strong>Your trip so far</strong>"
        "<ul style='margin:6px 0 0 0; padding-left:18px;'>{0}</ul></div>".format(
            rows),
        unsafe_allow_html=True,
    )


def handle_reply(replies, user_text):
    bot_text_parts = []
    st.session_state.messages.append({"role": "user", "content": user_text})
    for reply in replies:
        message = {"role": "assistant"}
        if "text" in reply:
            message["text"] = reply["text"]
            bot_text_parts.append(reply["text"])
        if "buttons" in reply:
            message["buttons"] = reply["buttons"]
        if "custom" in reply:
            message["custom"] = reply["custom"]
        st.session_state.messages.append(
            {"role": "assistant", "content": message})
    log_message(st.session_state.db_session, "user", user_text)
    log_message(st.session_state.db_session, "bot", " ".join(bot_text_parts))


def page_chat():
    st.title("Eco-Travel Advisor")
    st.caption("Plan low-carbon, sustainable trips. Ask about transport, "
               "accommodation, carbon footprint, offsets, or local experiences.")
    with st.expander("What do the colours mean?"):
        st.markdown(
            "- **Low emission (green):** a strong sustainable choice.\n"
            "- **Moderate (amber):** acceptable, but not the greenest.\n"
            "- **High emission (red):** consider a lower-carbon alternative.\n\n"
            "Carbon figures are approximate estimates to guide decisions, not "
            "certified measurements. You can ask to delete your data at any "
            "time, or ask how your data is handled.")

    for msg_index, message in enumerate(st.session_state.messages):
        if message["role"] == "user":
            with st.chat_message("user"):
                st.markdown(message["content"])
        else:
            content = message["content"]
            with st.chat_message("assistant"):
                if "text" in content:
                    st.markdown(content["text"])
                if "custom" in content:
                    custom = content["custom"]
                    kind = custom.get("type")
                    if kind == "recommendation":
                        render_recommendation(custom)
                    elif kind == "carbon_summary":
                        render_carbon_summary(custom)
                    elif kind == "handover":
                        render_handover(custom)
                    elif kind == "handover_summary":
                        render_handover_summary(custom)
                    elif kind == "date_request":
                        # Show a calendar range picker only for the latest
                        # message, so old pickers disappear as the chat moves on.
                        if msg_index == len(st.session_state.messages) - 1:
                            today = date.today()
                            chosen = st.date_input(
                                "Select your travel dates (start and end)",
                                value=(today + timedelta(days=7),
                                       today + timedelta(days=14)),
                                min_value=today,
                                key="dates_{0}".format(msg_index))
                            if st.button("Confirm dates",
                                         key="confirm_dates_{0}".format(msg_index)):
                                if isinstance(chosen, (list, tuple)) and len(chosen) == 2:
                                    start, end = chosen
                                    msg = "from {0} to {1}".format(
                                        start.isoformat(), end.isoformat())
                                    replies = send_to_rasa(msg)
                                    handle_reply(replies, msg)
                                    st.rerun()
                                else:
                                    st.warning("Please pick both a start and an "
                                               "end date.")
                if "buttons" in content:
                    # Only the latest message's buttons stay active, so stale
                    # buttons from earlier turns cannot be clicked by mistake.
                    is_last = msg_index == len(st.session_state.messages) - 1
                    cols = st.columns(len(content["buttons"]))
                    for index, button in enumerate(content["buttons"]):
                        if cols[index].button(button["title"],
                                              key="btn_{0}_{1}".format(
                                                  msg_index, index),
                                              disabled=not is_last):
                            replies = send_to_rasa(button["payload"])
                            handle_reply(replies, button["title"])
                            st.rerun()

    user_input = st.chat_input("Type your message")
    if user_input:
        replies = send_to_rasa(user_input)
        handle_reply(replies, user_input)
        st.rerun()


def page_dashboard():
    st.title("Eco dashboard")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Most common intents")
        intents = cached_query("most_common_intents")
        if not intents.empty:
            fig, ax = plt.subplots()
            ax.bar(intents["intent"], intents["total"], color="#2e7d32")
            ax.set_ylabel("messages")
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("No intent data available yet.")

    with col2:
        st.subheader("Average carbon by transport mode")
        modes = cached_query("average_carbon_by_mode")
        if not modes.empty:
            fig, ax = plt.subplots()
            ax.bar(modes["mode"], modes["avg_carbon_kg"], color="#1b5e20")
            ax.set_ylabel("kg CO2 (avg)")
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("No transport data available yet.")

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Hotel sustainability distribution")
        dist = cached_query("hotel_sustainability_distribution")
        if not dist.empty:
            fig, ax = plt.subplots()
            ax.bar(dist["score_band"], dist["hotels"], color="#43a047")
            ax.set_ylabel("hotels")
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("No hotel data available yet.")

    with col4:
        st.subheader("Cumulative trip plans over time")
        plans = cached_query("cumulative_trip_plans_by_day")
        if not plans.empty:
            fig, ax = plt.subplots()
            ax.plot(plans["day"], plans["cumulative_plans"], color="#2e7d32",
                    marker="o")
            ax.set_ylabel("cumulative plans")
            plt.xticks(rotation=45, ha="right")
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info("No trip plan data available yet.")

    st.subheader("Sustainability level breakdown")
    breakdown = cached_query("sustainability_level_breakdown")
    if not breakdown.empty:
        st.dataframe(breakdown, use_container_width=True)

    st.subheader("Top destinations")
    destinations = cached_query("top_destinations")
    if not destinations.empty:
        st.dataframe(destinations, use_container_width=True)

    st.subheader("Failed actions (audit)")
    failures = cached_query("failed_actions")
    if failures.empty:
        st.success("No failed actions recorded.")
    else:
        st.dataframe(failures, use_container_width=True)


def page_history():
    st.title("Trip history")
    plans = cached_sql(
        """
        SELECT plan_id, origin, destination, start_date, end_date, budget,
               sustainability_level, total_carbon_kg, status, created_at
        FROM TripPlan
        ORDER BY created_at DESC
        LIMIT 200;
        """
    )
    if plans.empty:
        st.info("No trip plans stored yet.")
        return

    destinations = ["All"] + sorted(
        [d for d in plans["destination"].dropna().unique()])
    selected = st.selectbox("Filter by destination", destinations)
    if selected != "All":
        plans = plans[plans["destination"] == selected]

    st.dataframe(plans, use_container_width=True)

    plan_ids = plans["plan_id"].tolist()
    if plan_ids:
        chosen = st.selectbox("Show items for plan", plan_ids)
        items = cached_sql(
            "SELECT item_type, description, price, carbon_kg "
            "FROM TripPlanItem WHERE plan_id = %(plan_id)s;",
            {"plan_id": int(chosen)},
        )
        st.dataframe(items, use_container_width=True)


def main():
    init_session()
    page = st.sidebar.radio(
        "Navigation", ["Chat", "Eco dashboard", "Trip history"])
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Your data is stored only to plan your trip and is handled in line "
        "with GDPR.")
    if page == "Chat":
        page_chat()
    elif page == "Eco dashboard":
        page_dashboard()
    else:
        page_history()


if __name__ == "__main__":
    main()
