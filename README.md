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
If you connect via WiFi to the node, you must edit the file ```config.toml``` first and enter the IP-Address of the node. If you use a serial connection, you can skip this step.
Run:
```
python nodebot.py
```
Write down the channel indexes. Press Ctrl+C several times to exit

## Edit config.toml
```
nano config.toml
```
Edit the channels section, set private admin and infochannels. Edit other values on your behalf. In general section set ```chanexit``` to ```false```. Save the file and run with ```python nodebot.py```

# Advanced configuration in config.toml
## Weather
Find a weather service, open the source code of the url that contains the text, set weather.split_left to the unique html text left of the text, the same for the right part. Set url and enable the service. Restart the bot.

## NINA Warnings
This is available in Germany only.
You need the 2-digit code of your state. Enter it into ninawarnings.state. You need an online json file containing all region keys. Enter that url into ninawarnings.keyurl. Now you need the URL to the NINA-Dashboard. Enter it into ninawarnings.dashurljson with a trailing slash. DO NOT include a filename like 12345.json. Now you need the URL to the NINA-Warning-Details. Enter it into ninawarnings.detailurljson with a trailing slash. DO NOT include a filename like 12345.json. Under [ninawarnings.regionnames] add the regionkey and the corresponding Name of each "Landkreis".
Enable the service.

# Run on startup on a RPi
If not already done, enable the rc.local service. Thereafter edit/create the file ```/etc/rc.local```:
```
#!/bin/sh -e
cd /home/pi/nodebot
python /home/pi/nodebot/nodebot.py &
exit 0
```
(Adjust the paths)

# Commands
## Public
* /info - Bot information
* /warnings - See list of warnings
* /stats - Bot statistics
* /ping - Request a pong
* /help - Help
* /echo <text> - Requet an echo response

## Responses
* test - Bot responds with a test message
* greetings - Sometimes (!) the bot answers a greeting

## Admin (Commands work in admin channel only)
* /ban <id> - Ban a user from the bot (the user can not issue any commandy) and the messages do not appear in the history API
* /unban <id> - Self explaining
* /banlist - List banned users
* /weathertest - Works in admin channel, tests weather retrieval
* /reboot - reboots the server (yep the server, not the bot)


