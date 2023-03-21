import json
import os.path

from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit, QCheckBox, \
    QTextEdit, QLabel
from PyQt5.QtGui import QTextCursor
from client import Client


class Gui:
    def __init__(self):
        # Initialize fields
        self.data = {
            "npub": ""
        }
        self.session_file_path = "session.json"
        self.title = "Nostrstats"

        # Load data
        self.load_data()

        # Create app
        self.app = QApplication([])
        self.app.setStyle("Fusion")

        #  Create window
        self.window = QWidget()
        self.window.setWindowTitle(self.title)

        # Create layout
        main_layout = QVBoxLayout()
        npub_row = QHBoxLayout()
        checkbox_column = QVBoxLayout()
        message_box_row = QVBoxLayout()

        # Create widgets
        self.npub_input = QLineEdit(self.data["npub"])
        self.npub_input.setPlaceholderText("User public key (npub)")
        self.npub_input.setFixedWidth(400)
        self.npub_input.textChanged.connect(self.save_npub)
        self.button = QPushButton('Run')
        self.button.clicked.connect(self.click_run)
        self.activity_on_npub_cb = QCheckBox("Activity (notifications) on npub by kind")
        self.minimum_neccessary_relays_cb = QCheckBox("Least necessary relays by followers")
        self.relays_of_followers_cb = QCheckBox("Relays of followers")
        message_box_label = QLabel("Status output")
        self.message_box = QTextEdit()
        self.message_box.setFixedHeight(100)
        self.message_box.setReadOnly(True)
        self.message_box.setStyleSheet("background-color: rgb(204, 204, 204);")

        # Add widgets to layout
        npub_row.addWidget(self.npub_input)
        npub_row.addWidget(self.button)
        checkbox_column.addWidget(self.activity_on_npub_cb)
        checkbox_column.addWidget(self.minimum_neccessary_relays_cb)
        checkbox_column.addWidget(self.relays_of_followers_cb)
        message_box_row.addWidget(message_box_label)
        message_box_row.addWidget(self.message_box)

        # Add layout to window
        main_layout.addLayout(npub_row)
        main_layout.addLayout(checkbox_column)
        main_layout.addLayout(message_box_row)
        self.window.setLayout(main_layout)

        # Show window
        self.window.show()

        # Run app
        self.app.exec()

        # Initialize empty client
        self.client = None

    def save_npub(self):
        """
        Saves user provided public key into the session's data.
        """
        self.data["npub"] = self.npub_input.text()
        with open(self.session_file_path, "w") as file:
            json.dump(self.data, file)

    def load_data(self):
        """
        Load the session's data.
        """
        if os.path.exists(self.session_file_path):
            with open(self.session_file_path, "r") as file:
                self.data = json.load(file)

    def click_run(self):
        """
        Parameterize and execute client code.
        """
        # Disable gui
        self.disable_gui()

        # Clear message output
        self.message_box.clear()

        # Get public key from gui
        npub = self.npub_input.text()

        # Get settings
        self.activity_on_npub_cb.isChecked()

        # Initialize client
        self.client = Client(self.window,
                             npub,
                             self.activity_on_npub_cb.isChecked(),
                             self.minimum_neccessary_relays_cb.isChecked(),
                             self.relays_of_followers_cb.isChecked())

        # Connect message box update to client
        self.client.log_messages.connect(self.on_log_emit)

        # Connect gui enabling to client finishing its task
        self.client.finished.connect(self.enable_gui)

        # Execute client
        self.client.start()

    def enable_gui(self):
        """
        Enable gui elements.
        """
        self.window.setWindowTitle(self.title)
        self.npub_input.setEnabled(True)
        self.button.setEnabled(True)
        self.activity_on_npub_cb.setEnabled(True)
        self.minimum_neccessary_relays_cb.setEnabled(True)
        self.relays_of_followers_cb.setEnabled(True)

    def disable_gui(self):
        """
        Disable gui elements.
        """
        self.window.setWindowTitle(self.title + " (Running)")
        self.npub_input.setEnabled(False)
        self.button.setEnabled(False)
        self.activity_on_npub_cb.setEnabled(False)
        self.minimum_neccessary_relays_cb.setEnabled(False)
        self.relays_of_followers_cb.setEnabled(False)

    def on_log_emit(self, f_msg):
        self.message_box.append(f_msg)
        self.message_box.moveCursor(QTextCursor.End)
