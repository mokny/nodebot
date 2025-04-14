# nodebot
A bot for meshtastic nodes

# Install
## Install dependencies (venv recommended)
```
pipx install "meshtastic[cli]"
pipx install flask
pipx install toml
```

## First Run 
```
python nodebot.py
```
Write down the channel indexes. Press Ctrl+C several times to exit

## Edit config.toml
```
nano config.toml
```
Edit the channels section, set private admin and infochannels. Edit other values on your behalf. In general section set ```chanexit``` to ```false```. Save the file and run with ```python nodebot.py```


