# LumaBeat
IOT Project by Ronel Yust

LumaBeat is a Python application designed to control a smart LED lamp and change its color to the beat of songs.

## Features
- Three Types of emulators :
  - Control buttons: "Play" and "Stop/Continue" buttons to control song playback.
  - Relay emulator: Represents the state of the light (on/off).
  - Light visualization: Shows color changes corresponding to the music beat in the Main GUI.
- Data Manager: Connects to the MQTT broker, processes messages, and sends warnings/alarms.
- Main GUI: Displays real-time data, messages, warnings, and alarms.
- Local database: Saves all MQTT messages using SQLite.
- Song player: Allows users to load and play songs in MP3, WAV, or OGG formats.
- Song analyzer: Runs on a separate thread to analyze the beats and send MQTT messages based on beat changes.
- Auto-connection: Automatically connects to the MQTT broker at broker.hivemq.com, port 1883.

## Prerequisites

- Python
- A song in the format of MP3, WAV or OGG.

## Usage

Open the application and wait for it to automatically connect to the MQTT broker.

Load a song of your choosing.

Hit the "Play" button and watch as the lights change according to the beat of the song.

You can pause the song at any time, pressing "Continue" will resume playback and continue the light synchronization.

Monitor all MQTT messages in the message box.

All messages are automatically saved in the local SQLite database (messages.db).


## Video Demo

Watch a demonstration of LumaBeat in action on https://youtu.be/afFJjLhAtgk​

![Video Thumbnail](https://img.youtube.com/vi/afFJjLhAtgk/hqdefault.jpg)



## Technologies Used
[![My Skills](https://skillicons.dev/icons?i=py,sqlite)](https://skillicons.dev)



