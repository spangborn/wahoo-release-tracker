import requests
import sqlite3
import json
import time
import xml.etree.ElementTree as ET
import pytz
from datetime import datetime
import os
from atproto import Client, models
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Mapping of URLs to device names
URLS = {
    "elemnt": "https://bolt.wahoofitness.com/boltapp/version.json",
    "bolt": "https://bolt.wahoofitness.com/boltapp/version.json-bolt",
    "bolt2": "https://bolt.wahoofitness.com/boltapp/version.json-bolt2",
    "roam": "https://bolt.wahoofitness.com/boltapp/version.json-roam",
    "roam1.1": "https://bolt.wahoofitness.com/boltapp/version.json-roam1.1",
    "roam2": "https://bolt.wahoofitness.com/boltapp/version.json-roam2",
    "ace": "https://bolt.wahoofitness.com/boltapp/version.json-ace"
}

# SQLite database file
DB_FILE = "versions.db"
RSS_FILE = "versions.rss"

PUSHOVER_USER_KEY = os.getenv('PUSHOVER_USER_KEY')
PUSHOVER_API_TOKEN = os.getenv('PUSHOVER_API_TOKEN')
BLUESKY_USERNAME = os.getenv('BLUESKY_USERNAME')
BLUESKY_APP_PASSWORD = os.getenv('BLUESKY_APP_PASSWORD')

client = None

def init_db():
    """Initialize the SQLite database and create the necessary table."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device TEXT NOT NULL,
            version TEXT NOT NULL,
            url TEXT NOT NULL,
            release_type TEXT NOT NULL,
            first_seen TIMESTAMP DEFAULT (datetime('now', 'localtime')),
            UNIQUE(device, version, release_type)
        )
    ''')
    conn.commit()
    conn.close()

def fetch_version_data(url):
    """Fetch JSON data from a given URL."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None

def send_pushover_alert(device, version, release_type):
    """Send a Pushover alert for a new firmware version."""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("Pushover user key or API token not set.")
        return

    message = f"New firmware version for {device}: {version} ({release_type})"
    data = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "message": message,
    }

    try:
        response = requests.post("https://api.pushover.net/1/messages.json", data=data)
        response.raise_for_status()
        print("Pushover alert sent.")
    except requests.RequestException as e:
        print(f"Error sending Pushover alert: {e}")

def login_to_bluesky():
    """Login to BlueSky and return the client."""
    global client
    if not BLUESKY_USERNAME or not BLUESKY_APP_PASSWORD:
        print("BlueSky username or app password not set.")
        return None

    try:
        client = Client()
        client.login(BLUESKY_USERNAME, BLUESKY_APP_PASSWORD)
        print("Logged into BlueSky.")
        return client
    except Exception as e:
        print(f"Error logging into BlueSky: {e}")
        return None

def post_to_bluesky(device, version, release_type):
    """Post a new firmware version to BlueSky using the atproto package."""
    global client
    if client is None:
        client = login_to_bluesky()
        if client is None:
            return

    message = f"New firmware version for {device}: {version} ({release_type})"
    
    try:
        
        client.send_post(text=message)
        print("Posted to BlueSky.")
    except Exception as e:
        print(f"Error posting to BlueSky: {e}")
        # Attempt to re-login and post again
        client = login_to_bluesky()
        if client:
            try:
                client.send_post(text=message)
                print("Posted to BlueSky after re-login.")
            except Exception as e:
                print(f"Error posting to BlueSky after re-login: {e}")

def store_version(device, version, apk_url, release_type):
    """Store the version in the database if it's new."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO versions (device, version, url, release_type) VALUES (?, ?, ?, ?)",
            (device, version, apk_url, release_type)
        )
        conn.commit()
        print(f"New version recorded: {device} - {version} ({release_type})")
        
        if PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN:
            send_pushover_alert(device, version, release_type)
            
        if BLUESKY_USERNAME and BLUESKY_APP_PASSWORD:    
            post_to_bluesky(device, version, release_type)

    except sqlite3.IntegrityError:
        print(f"Version {version} ({release_type}) for {device} already recorded.")
    finally:
        conn.close()

def generate_rss():
    """Generate an RSS feed with the versions found."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT device, version, url, release_type, first_seen FROM versions ORDER BY first_seen DESC LIMIT 100")
    entries = cursor.fetchall()
    conn.close()

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Wahoo Versions RSS Feed"
    ET.SubElement(channel, "link").text = "https://example.com/versions.rss"
    ET.SubElement(channel, "description").text = "Latest firmware versions for Wahoo devices."

    local_tz = pytz.timezone('America/Denver')  # Replace with your local timezone

    for device, version, url, release_type, first_seen in entries:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = f"{device} - {version} ({release_type})"
        ET.SubElement(item, "link").text = url
        ET.SubElement(item, "description").text = f"Version {version} ({release_type}) for {device}"
        
        # Convert timestamp to local timezone
        dt = datetime.strptime(first_seen, "%Y-%m-%d %H:%M:%S")
        dt = pytz.utc.localize(dt).astimezone(local_tz)
        ET.SubElement(item, "pubDate").text = dt.strftime("%a, %d %b %Y %H:%M:%S %z")

    tree = ET.ElementTree(rss)
    tree.write(RSS_FILE, encoding="utf-8", xml_declaration=True)
    print("RSS feed updated.")

def main():
    """Main polling function."""
    init_db()
    new_version_recorded = False
    for device, url in URLS.items():
        data = fetch_version_data(url)

        if data:
            for release_type in ["std", "beta", "alpha"]:
                version_key = f"{release_type}-version"
                url_key = f"{release_type}-url"
                if version_key in data and url_key in data:
                    try:
                        store_version(device, data[version_key], data[url_key], release_type)
                        new_version_recorded = True
                    except sqlite3.IntegrityError:
                        continue
        else:
            print(f"Invalid data from {url}")

    if new_version_recorded:
        generate_rss()

if __name__ == "__main__":
    main()