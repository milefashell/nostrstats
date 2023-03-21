# Nostrstats
This is a python tool with a GUI to retrieve nostr statistics for a specific public key.

## Available statistics
* Activity of other accounts on a certain npub (only npubs own relays are used for search)
* Define the least necessary number of relays that a certain npub needs to be able to reach all it's followers
* Show all relays of followers in sorted order (sorted by number of followers using relay)

## Run
Run `main.exe`. 

You can also run `main.py` as well after python installation defined below.

## Install
You will need a `python 3.9`. Then install the requirements. (Python virtual environment is suggested.)
```commandline
pip install -r requirements.txt
```

## Build locally
### Windows
```commandline
pyinstaller.exe --onefile -w --clean --add-binary=".\venv\Lib\site-packages\coincurve\libsecp256k1.dll;coincurve" main.py
```
