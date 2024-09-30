import sys
import random
import time
import paho.mqtt.client as mqtt
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel, QFileDialog, QMessageBox, QTextEdit
from PyQt5.QtGui import QTextCursor
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QMetaObject, Q_ARG
import pygame
import queue
import aubio
import threading
from mutagen.mp3 import MP3
import sqlite3  

# Database Manager Class that saves the messages from the broker to a local SQL database.
class DatabaseManager:
    def __init__(self, db_name="messages.db"):
        # Initializing the database connection and creating the messages table
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_table()

        # A queue for handling database operations in a separate thread
        self.db_queue = queue.Queue()
        self.running = True
        self.worker_thread = threading.Thread(target=self.process_queue)
        self.worker_thread.start()

    def create_table(self):
        # If there is no table - create one
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT,
                message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def save_message(self, topic, message):
        # Saving a message to the queue
        self.db_queue.put((topic, message))

    def process_queue(self):
        # Continuously process messages in the queue and save to the database
        while self.running:
            try:
                # Wait for an item from the queue
                topic, message = self.db_queue.get(timeout=1)  
                self.cursor.execute('''
                    INSERT INTO messages (topic, message) VALUES (?, ?)
                ''', (topic, message))
                self.conn.commit()
            except queue.Empty:
                continue


    def close(self):
        # Shut down the Datamanager
        self.running = False
        self.worker_thread.join()
        self.conn.close()

# Create a unique client name
global clientname
r = random.randrange(1, 100000)
clientname = "IOT_client-Id-" + str(r)

# MQTT Client Class
class MqttClient:
    def __init__(self, broker, port, main_window, username='', password=''):
        # Initialize a MQTT client with broker details and credentials
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.main_window = main_window
        self.client = mqtt.Client(clientname)
        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.connected = False

    def on_connect(self, client, userdata, flags, rc):
        # Called when the client connects to the MQTT broker
        if rc == 0:
            self.connected = True
            print("Connected to MQTT Broker!")
            QMetaObject.invokeMethod(self.main_window, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, "Connected to MQTT broker"))
            
            self.client.subscribe("smartlamp/led")
            self.client.subscribe("smartlamp/led/colors")  # Subscribe to colors topic
            self.client.subscribe("smartlamp/led/status")  # Subscribe to status topic
        else:
            self.connected = False
            print(f"Failed to connect, return code {rc}")
            QMetaObject.invokeMethod(self.main_window, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, f"Failed to connect, return code {rc}"))            

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print("Disconnected from MQTT Broker")
        QMetaObject.invokeMethod(self.main_window, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, "Disconnected from MQTT broker"))

    def on_message(self, client, userdata, msg):
        message = f"Received message: {msg.payload.decode()} on topic {msg.topic}"
        self.main_window.database_manager.save_message(msg.topic, msg.payload.decode())

        # Handle relay status updates from the broker
        if msg.topic == "smartlamp/led/status":
            relay_status = msg.payload.decode()  
            QMetaObject.invokeMethod(self.main_window, "update_relay_status", Qt.QueuedConnection, Q_ARG(str, relay_status))
            status_message = f"Relay status changed: {relay_status}"
            QMetaObject.invokeMethod(self.main_window, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, status_message))
    
        # Handle color changes
        elif msg.topic == "smartlamp/led/colors":
            color_message = f"Color changed to: {msg.payload.decode()}"
            QMetaObject.invokeMethod(self.main_window, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, color_message))
    
        # Display the full message in the message box for any other messages
        QMetaObject.invokeMethod(self.main_window, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, message))

    def connect(self):
        try:
            print(f"Connecting to {self.broker}:{self.port}")
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"Connection failed: {e}")
            QMetaObject.invokeMethod(self.main_window, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, f"Connection failed: {e}"))

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, topic, message):
        if self.connected:
            self.client.publish(topic, message)
            print(f"Published '{message}' to topic '{topic}'")
        else:
            print("Cannot publish, MQTT client not connected.")

# Main Window (GUI) Class
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Smart LED Lamp Controller")
        self.setGeometry(100, 100, 600, 400)

        # Initialize MQTT client and connect right away
        self.mqtt_broker = "broker.hivemq.com"
        self.mqtt_port = 1883

        self.mqtt_client = MqttClient(self.mqtt_broker, self.mqtt_port, self)
        self.mqtt_client.connect()

        self.database_manager = DatabaseManager() 

        # Setup the UI components
        self.setup_ui()

        # Initialize the pygame mixer
        pygame.mixer.init()

        # Variable to store the path of the loaded song
        self.song_path = ""

        # Thread control
        self.analysis_thread = None
        self.running = False
        self.paused = False  

        # Control for beat detection
        self.should_pause_analysis = threading.Event()  
        self.should_pause_analysis.set() 

        # Defining the colors of the lamp
        self.colors = ["red", "orange", "yellow", "green", "blue", "indigo", "violet"]
        self.current_color_index = 0 
        
        # Variables to store beat information
        self.last_beat_time = 0
        self.beat_count = 0

        # Relay state
        self.relay_on = False  

    def setup_ui(self):
        layout = QVBoxLayout()

        # Status label to show MQTT connection status
        self.status_label = QLabel("Connecting to MQTT broker...")
        layout.addWidget(self.status_label)

        # Update MQTT status based on connection
        self.check_mqtt_connection()

        # Create a load song button
        self.load_song_button = QPushButton("Load Song", self)
        self.load_song_button.clicked.connect(self.load_song)
        layout.addWidget(self.load_song_button)

        # Create a play button
        self.play_button = QPushButton("Play", self)
        self.play_button.clicked.connect(self.play_song)
        layout.addWidget(self.play_button)

        # Create a stop button (which also serves as continue)
        self.stop_button = QPushButton("Stop", self)
        self.stop_button.clicked.connect(self.stop_or_continue_song)
        layout.addWidget(self.stop_button)

        # Add beat detection visualizer (information about the beat)
        self.beat_info_label = QLabel("Beat Info: ", self)
        self.beat_info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.beat_info_label)

        # Create a text area to show MQTT messages
        self.mqtt_message_box = QTextEdit(self)
        self.mqtt_message_box.setReadOnly(True)
        layout.addWidget(self.mqtt_message_box)

        # Lamp visualization (color-changing area)
        self.lamp_label = QLabel("LED Lamp Visual", self)
        self.lamp_label.setStyleSheet("background-color: grey;")
        self.lamp_label.setAlignment(Qt.AlignCenter)
        self.lamp_label.setFixedHeight(100)
        layout.addWidget(self.lamp_label)

        # Relay visualization
        self.relay_label = QLabel("Relay Status", self)
        self.relay_label.setStyleSheet("background-color: red;")
        self.relay_label.setAlignment(Qt.AlignCenter)
        self.relay_label.setFixedHeight(50)
        layout.addWidget(self.relay_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def check_mqtt_connection(self):
        # Check if the MQTT client is connected and update the status label
        if self.mqtt_client.connected:
            self.status_label.setText("Connected to MQTT broker")
        else:
            self.status_label.setText("Failed to connect to MQTT broker")
        QTimer.singleShot(1000, self.check_mqtt_connection)

    def load_song(self):
        # Load a song file using a file dialog
        file_dialog = QFileDialog(self)
        self.song_path, _ = file_dialog.getOpenFileName(self, "Open Audio File", "", "Audio Files (*.mp3 *.wav *.ogg)")

        if self.song_path:
            print(f"Loaded song: {self.song_path}")
            self.song_duration = self.get_song_duration(self.song_path)
            QMessageBox.information(self, "Song Loaded", f"Loaded song: {self.song_path}\nDuration: {self.song_duration:.2f} seconds")
        else:
            QMessageBox.warning(self, "No Song Loaded", "No song was selected.")

    def get_song_duration(self, song_path):
        audio = MP3(song_path)
        return audio.info.length

    def play_song(self):
        if not self.mqtt_client.connected:
            QMessageBox.warning(self, "MQTT Not Connected", "Cannot start, MQTT is not connected.")
            return

        if not self.song_path:
            QMessageBox.warning(self, "No Song Loaded", "Please load a song first.")
            return

        # Publish relay status to MQTT when the song starts = Play button is an Emulator that sends message.
        self.mqtt_client.publish("smartlamp/led/status", "on") 

        # Play the selected song using pygame
        pygame.mixer.music.load(self.song_path)
        pygame.mixer.music.play()

        self.paused = False  # Reset paused state when starting the song

        # Start audio analysis in a separate thread
        self.running = True
        self.analysis_thread = threading.Thread(target=self.analyze_song)
        self.analysis_thread.start()

    def analyze_song(self):
        win_s = 512  
        hop_s = win_s // 2  
        samplerate = 44100

        # Aubio's beat detection
        beat_detection = aubio.tempo("default", win_s, hop_s, samplerate)

        # Source (audio stream)
        s = aubio.source(self.song_path, samplerate, hop_s)

        while self.running:
            # Wait here if analysis should be paused
            self.should_pause_analysis.wait()  

            samples, read = s()
            if read == 0 or not pygame.mixer.music.get_busy():
                break

            is_beat = beat_detection(samples)
            if is_beat[0]:
                # Get current position in seconds
                current_time = pygame.mixer.music.get_pos() / 1000.0  
                self.beat_count += 1
                
                # Calculate BPM
                frequency = 60 / (current_time - self.last_beat_time) if self.last_beat_time else 0
                self.last_beat_time = current_time

                # Create a beat information message
                beat_info = f"Beat #{self.beat_count}: Timestamp: {current_time:.2f}, Frequency: {frequency:.2f} BPM"
                
                # Update the beat information label
                QMetaObject.invokeMethod(self, "update_beat_info", Qt.QueuedConnection, Q_ARG(str, beat_info))

                # Determine the new color
                self.current_color_index = (self.current_color_index + 1) % len(self.colors)
                color = self.colors[self.current_color_index]

                # Log the color change message
                QMetaObject.invokeMethod(self, "display_color_change_message", Qt.QueuedConnection, Q_ARG(str, color))

                # Change lamp color
                QMetaObject.invokeMethod(self, "update_lamp_color", Qt.QueuedConnection, Q_ARG(str, color))

            time.sleep(0.01)

        self.running = False
        self.update_lamp_color("grey")
        pygame.mixer.music.stop()

    @pyqtSlot(str)
    def update_beat_info(self, info):
        self.beat_info_label.setText(info)

    @pyqtSlot(str)
    def display_color_change_message(self, color):
        message = f"Changing lamp color to {color}"
        # Send the new color to MQTT
        self.mqtt_client.publish("smartlamp/led/colors", color)  
        QMetaObject.invokeMethod(self, "append_mqtt_message", Qt.QueuedConnection, Q_ARG(str, message))

    @pyqtSlot(str)
    def append_mqtt_message(self, message):
        self.mqtt_message_box.append(message)

    @pyqtSlot(str)
    def update_lamp_color(self, color):
        self.lamp_label.setStyleSheet(f"background-color: {color};")
        print(f"Lamp color changed to: {color}")

    @pyqtSlot(str)
    def update_relay_status(self, status):
        """ Update the relay visualization based on the received status. """
        if status.lower() == "on":
            self.relay_on = True
            self.relay_label.setStyleSheet("background-color: green;")
            print("Relay is ON")
        elif status.lower() == "off":
            self.relay_on = False
            self.relay_label.setStyleSheet("background-color: red;")
            print("Relay is OFF")

    def stop_or_continue_song(self):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            # Pause analysis
            self.should_pause_analysis.clear()  
            self.stop_button.setText("Continue")

            # Publish relay status to MQTT
            self.mqtt_client.publish("smartlamp/led/status", "off")
            self.paused = True
        else:
            pygame.mixer.music.unpause()
            # Resume analysis
            self.should_pause_analysis.set()  
            self.stop_button.setText("Stop")

            # Publish relay status to MQTT
            self.mqtt_client.publish("smartlamp/led/status", "on")
            self.paused = False

    def closeEvent(self, event):
        self.running = False
        if self.analysis_thread is not None:
            # Ensure the analysis thread finishes before closing
            self.analysis_thread.join() 
        # Disconnect MQTT client 
        self.mqtt_client.disconnect() 
        # Close the database manager 
        self.database_manager.close() 
        # Accept the event to close the window
        event.accept()  

    @pyqtSlot(str)
    def display_mqtt_message(self, message):
        self.mqtt_message_box.append(message)

# Entry point
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())