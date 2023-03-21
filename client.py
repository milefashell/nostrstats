# General imports
import os
import json
import time
import uuid
import logging
import asyncio
import threading
import pandas as pd
import numpy as np
from urllib import parse
import plotly.offline
import plotly.graph_objects as go
from yattag import Doc
from PyQt5.QtCore import pyqtSignal, QThread

# Nostr imports
from pynostr.relay_manager import RelayManager, log
from pynostr.key import PublicKey
from pynostr.filters import FiltersList, Filters
from pynostr.event import EventKind

# Set pandas plotting library
pd.options.plotting.backend = "plotly"

# Set debug level
log.setLevel(logging.FATAL)

# Initialize default relays
DEFAULT_RELAYS = [
    "wss://nos.lol",
    "wss://nostr.mom",
    "wss://relay.austrich.net",
    "wss://nostr-pub.wellorder.net",
    "wss://relay.damus.io",
    "wss://nostr.bitcoiner.social"]


class Client(QThread):
    log_messages = pyqtSignal(object)
    finished = pyqtSignal(bool)

    def __init__(self, f_parent, f_npub, f_activity_on_npub, f_necessary_relays, f_relays_of_followers):
        QThread.__init__(self, f_parent)

        # Initialize output folder
        self.output_folder = "./output/"

        # Initialize parent
        self.parent = f_parent

        # Initialize fields
        self.npub = f_npub
        self.activity_on_npub = f_activity_on_npub
        self.necessary_relays = f_necessary_relays
        self.relays_of_followers = f_relays_of_followers

        # Initialize relay manager
        self.relay_manager = RelayManager()

        # Wait time
        self.wait_time = 1

    def load_config(self) -> dict:
        """
        Load configuration file.
        """
        config_file = "config.json"
        data = {"relays": DEFAULT_RELAYS}

        # Load relays from config file if exist
        if os.path.exists(config_file):
            try:
                data = json.load(open(config_file, "r"))
            except:
                pass
        # Create config file from default relays if does not exist
        else:
            json.dump(data, open(config_file, "w"))

        return data

    def add_relays(self, f_relay_list):
        """
        Add relays to internal relay manager.

        @param f_relay_list: List of relay urls.
        """
        # Close all relay connections
        self.relay_manager.close_all_relay_connections()

        # Delete closed relays
        self.relay_manager.remove_closed_relays()

        # Add new relays
        for relay in f_relay_list:
            self.relay_manager.add_relay(relay, timeout=30)

    def hex_from_npub(self, f_npub):
        """
        Convert provided npub to hex.

        If it is already hex, return the same hex back.

        @param f_npub: String of public key in npub form.
        @return: Public key in hex form.
        """
        if f_npub.startswith("npub"):
            pub_hex = PublicKey.from_npub(f_npub).hex()
        else:
            pub_hex = f_npub
        return pub_hex

    def get_notes(self, f_filter_list: FiltersList):
        """
        Get notes for the provided filter list.

        @param f_filter_list: List of filters to send to relays for querying.
        @return: Dictionary of parsed events. (Key is event id)
        """
        # Get relay count
        relay_count = len(self.relay_manager.relays)

        # Initialize eose count
        eose_count = 0

        # Initialize output
        events = {}

        # Run until at least half of the relays respond
        while eose_count < relay_count * 0.5:
            # Reset output events dictionary
            events = {}

            # Send subscription
            subscription_id = uuid.uuid1().hex
            self.relay_manager.add_subscription_on_all_relays(subscription_id, f_filter_list)
            self.relay_manager.run_sync()
            time.sleep(self.wait_time)

            # Get all eose
            all_eose = self.relay_manager.message_pool.get_all_eose()
            eose_count = len(all_eose)

            # Get all notices
            all_notices = self.relay_manager.message_pool.get_all_notices()

            # Get all ok
            all_oks = self.relay_manager.message_pool.get_all_ok()

            while self.relay_manager.message_pool.has_events():
                event_msg = self.relay_manager.message_pool.get_event()
                events[event_msg.event.id] = event_msg.event

            self.relay_manager.close_subscription_on_all_relays(subscription_id)
            self.relay_manager.close_all_relay_connections()

        return events

    def get_own_relays(self):
        """
        Get relays of own public key.

        @return: List of relay urls.
        """
        npub_hex = self.hex_from_npub(self.npub)

        relays_per_user = self.get_relays([npub_hex])

        return relays_per_user[npub_hex]

    def get_relays(self, f_authors):
        """
        Get relays for provided authors.

        @param f_authors: Authors to get relays of.
        @return: Dictionary of relays. (Keys are author hex public key)
        """
        filters = FiltersList([Filters(kinds=[EventKind.CONTACTS],
                                       authors=f_authors)])
        events = self.get_notes(filters)

        relays_per_user = {}
        for event_id, event in events.items():
            if (event.pubkey not in relays_per_user or
                relays_per_user[event.pubkey].created_at < event.created_at) \
                and len(event.content) > 0:
                relays_per_user[event.pubkey] = event

        output = {}
        for pub, event in relays_per_user.items():
            output[pub] = list(json.loads(event.content).keys())

        return output

    def get_notifications(self):
        """
        Get notifications for current public key.

        @return: Dataframe with all of the notifications.
        """
        npub_hex = self.hex_from_npub(self.npub)
        filters = FiltersList([Filters(kinds=[EventKind.ZAPPER, EventKind.TEXT_NOTE, EventKind.REACTION],
                                       pubkey_refs=[npub_hex])])
        events = self.get_notes(filters)

        data = []
        for event_id, event in events.items():
            if event.pubkey != npub_hex:
                data.append(event.__dict__)
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["created_at"], unit="s")
        df["time"] = df["date"].dt.time
        return df

    def get_follower_and_their_relays(self):
        """
        Get current users followers, and their relays.

        @return: List of following hex public keys, Dictionary of relays (Hex public key as key)
        """
        npub_hex = self.hex_from_npub(self.npub)
        filters = FiltersList([Filters(kinds=[EventKind.CONTACTS],
                                       pubkey_refs=[npub_hex])])
        events = self.get_notes(filters)

        following = set()
        relays_per_user = {}
        for event_id, event in events.items():
            following.add(event.pubkey)

            if (event.pubkey not in relays_per_user or
                relays_per_user[event.pubkey].created_at < event.created_at) \
                and len(event.content) > 0:
                relays_per_user[event.pubkey] = event

        output = {}
        for pub, event in relays_per_user.items():
            output[pub] = list(json.loads(event.content).keys())

        return list(following), output

    def get_notification_stats(self, f_notif_df):
        """
        Get statistics for the provided notifications

        @param f_notif_df: Notifications dataframe.
        @return: Dictionary for html generation.
        """
        # Initialize event kind types and names for them
        event_types = {EventKind.REACTION: "Reaction", EventKind.TEXT_NOTE: "Comment", EventKind.ZAPPER: "Zap"}

        # Find time of notifications
        time_df = f_notif_df.set_index("date")

        output = {}
        fig = go.Figure()
        for t, kind_text in event_types.items():
            # Calculate data to plot
            data = time_df[time_df["kind"] == t]
            data = data[["pubkey"]]
            aggregate = data.groupby(data.index.floor('15Min').time).count()
            all_count = sum(aggregate["pubkey"])
            aggregate[kind_text] = aggregate["pubkey"] * 100 / all_count

            fig.add_trace(go.Bar(x=aggregate.index, y=aggregate[kind_text], name=kind_text))

        fig.update_layout(title={"text": "Activity of followers by activity type",
                                 'y': 0.92,
                                 'x': 0.5,
                                 'xanchor': 'center',
                                 'yanchor': 'top',
                                 'font': {
                                     'size': 24
                                 }
                                 })
        fig.update_xaxes(title_text='Time')
        fig.update_yaxes(title_text='Activity intensity [%]')
        div_code = plotly.offline.plot(fig, include_plotlyjs=False, output_type="div")

        output["Activity of followers by activity type"] = {
            "type": "image",
            "div": div_code,
            "description": """Notifications from connected relays are collected for comments, zaps, and reactions. 
They are filtered for certain "Kind" type and grouped by time for the public keys. The data is plotted on a bar chart.
"""
        }

        return output

    def get_relay_statistics(self, f_relays_by_pub):
        """
        Get statistics for relays of followers.

        @param f_relays_by_pub: Dictionary of relays. (Hey public key as key).
        @return: Dictionary for html generation.
        """
        # Initialize output
        output = {}

        # Generate dataframe out of relay per pubkey usage
        result = {}
        for pub, relays in f_relays_by_pub.items():
            result[pub] = {}
            for relay in relays:
                relay = parse.urlparse(relay).hostname
                result[pub][relay] = 1
        df = pd.DataFrame(result)
        df = df.fillna(0)

        # Calculate and sort count of public keys per relay
        df["Count"] = df.sum(axis=1)
        df = df.sort_values(["Count"], ascending=False)

        if self.relays_of_followers:
            # Export relays of followers
            fig = go.Figure()
            counts = df[["Count"]]
            counts = counts.reset_index()
            counts.columns = ["Relay name", "Number of followers using the relay"]
            fig.add_table(header=dict(values=counts.columns),
                          cells=dict(values=[counts["Relay name"], counts["Number of followers using the relay"]]))
            fig.update_layout(title={"text": "Relay of followers",
                                     'y': 0.92,
                                     'x': 0.5,
                                     'xanchor': 'center',
                                     'yanchor': 'top',
                                     'font': {
                                         'size': 24
                                     }},
                              height=counts.shape[0]
                              )
            div_code = plotly.offline.plot(fig, include_plotlyjs=False, output_type="div")
            output["Relays of followers"] = {
                "type": "image",
                "div": div_code,
                "description": """Relays of followers are retrieved. Sorted in descending order by number of followers.
Visualized in a table."""
            }

        if self.necessary_relays:
            # Calculate the minimum relays that covers all followers
            new_df = df.copy()
            minimum_necessary_relays = {}
            while new_df["Count"].iloc[0] > 0:
                relay = new_df.index[0]
                values = new_df.values[0]
                new_df = new_df.drop([relay], axis=0)
                minimum_necessary_relays[relay] = {}
                columns_to_drop = np.array(new_df.columns)[values > 0]
                new_df = new_df.drop(columns_to_drop, axis=1)
                new_df["Count"] = new_df.sum(axis=1)
                new_df = new_df.sort_values(["Count"], ascending=False)

            for relay in minimum_necessary_relays:
                minimum_necessary_relays[relay]["Number of followers"] = df["Count"][relay]

            minimum_necessary_relays = pd.DataFrame(minimum_necessary_relays).transpose()

            # Export relays of followers
            minimum_necessary_relays = minimum_necessary_relays.reset_index()
            minimum_necessary_relays.columns = ["Relay name", "Number of followers using the relay"]
            fig = go.Figure()
            fig.add_table(header=dict(values=minimum_necessary_relays.columns),
                          cells=dict(values=[minimum_necessary_relays["Relay name"],
                                             minimum_necessary_relays["Number of followers using the relay"]]))
            fig.update_layout(title={"text": "Minimum necessary relays to reach all followers",
                                     'y': 0.92,
                                     'x': 0.5,
                                     'xanchor': 'center',
                                     'yanchor': 'top',
                                     'font': {
                                         'size': 24
                                     }},
                              height=400
                              )
            div_code = plotly.offline.plot(fig, include_plotlyjs=False, output_type="div")
            output["Minimum necessary relays to reach all followers"] = {
                "type": "image",
                "div": div_code,
                "description": """The last used relays of all followers are collected. The relay combination is searched 
 that is the smallest subset, that all of the followers have. Relays are plotted in a table with follower count for 
each.
    """
            }

        return output

    def calculate_stats(self):
        """
        Calculate user selected statistics.
        """
        # Create output
        output = {}

        if self.activity_on_npub:
            # Log to gui
            self.log_messages.emit("STARTED: Activity (notifications) on npub.")

            # Get notifications
            self.log_messages.emit("1.) Retrieving notifications for npub.")
            notif_df = self.get_notifications()

            # Get notification statistics
            self.log_messages.emit("2.) Generating plots for notifications.")
            output.update(self.get_notification_stats(notif_df))

            # Log to gui
            self.log_messages.emit("FINISHED: Activity (notifications) on npub.")

        if self.necessary_relays or self.relays_of_followers:
            # Log to gui
            self.log_messages.emit("STARTED: Relay statistics")

            # Get followings and their relays
            self.log_messages.emit("1.) Retrieving followers and their relays.")
            followers, relays_by_pub = self.get_follower_and_their_relays()

            # Get necessary relay statistics
            self.log_messages.emit("2.) Generating plots for relays.")
            output.update(self.get_relay_statistics(relays_by_pub))

            # Log to gui
            self.log_messages.emit("FINISHED: Least necessary relays")

        # Export result to html
        self.log_messages.emit("Generating output html.")
        self.export_html(output)

        self.log_messages.emit("Statistics generation finished!")

    def export_html(self, f_data: dict):
        """
        Export html report for dictionary.

        @param f_data: Dictionary containing the plots to export into an html document.
        """
        doc, tag, text = Doc().tagtext()

        doc.asis('<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>')
        with tag("body"):
            with tag("p"):
                text(f"Report for: {self.npub}")
            with tag("p"):
                text("Plots are interactive.")
            for title, data in f_data.items():
                if data["type"] == "image":
                    with tag("div"):
                        doc.asis(data["div"])
                with tag("h3"):
                    text("Description")
                with tag("p"):
                    text(data["description"])

        if not os.path.exists(self.output_folder):
            os.makedirs(self.output_folder)

        with open(os.path.join(self.output_folder, "index.html"), "w") as file:
            file.writelines(doc.getvalue())

    def run(self) -> None:
        """
        Execute client code.
        """
        # Create even thread for relay management
        asyncio.set_event_loop(asyncio.new_event_loop())

        try:
            # Load config
            config = self.load_config()

            # Add startup relays
            self.log_messages.emit("Load default relays.")
            self.add_relays(config["relays"])

            # Get current relays for pubkey
            self.log_messages.emit("Retrieve users own relays.")
            current_relays = self.get_own_relays()

            # Set current relays for public key
            self.log_messages.emit("Load user's own relays.")
            self.add_relays(current_relays)

            # Export statistics for public key
            self.log_messages.emit("Start statistics calculation.")
            self.calculate_stats()

            # Open output in browser
            os.system(f"start {os.path.join(self.output_folder, 'index.html')}")

            # Enable parent gui
            self.finished.emit(True)
        except Exception as e:
            print(e)
            self.log_messages.emit(str(e))
