# Wahoo Release Tracker

This project polls the various Wahoo ELEMNT boltapp.json URLS for new firmware releases for standard, beta, and alpha. They're then logged in the sqlite DB along with a timestamp of when they were first seen.

An RSS feed is also generated for tracking purposes.

## How to run

The best practice is using a virtualenv (venv) to reduce impacts on the system python modules.

`python3 -m venv venv`
`source venv/bin/activate`
`pip install -r requirements.txt`
`python3 update.py`

## Output

The script will produce a versions.db sqlite3 database and a versions.rss file