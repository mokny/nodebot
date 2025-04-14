import time
import meshtastic
import meshtastic.tcp_interface
import meshtastic.serial_interface

from pubsub import pub
import json
from flask import Flask, jsonify, request
from datetime import datetime
import threading
import html
import textwrap
import vars
import random
import logging
import os
import requests
import base64
import json
import hashlib
import toml
import codecs

vars.clearlog()
vars.log('================================')
vars.log('      NodeBot ' + vars.vrsn)
vars.log('      by Till')
vars.log('      https//mesh-nrw.de')
vars.log('================================')

vars.tomlraw = ''

with open("config.toml") as f:
    vars.tomlraw = f.read()

vars.config = toml.loads(vars.tomlraw)


log = logging.getLogger('werkzeug')

if not vars.config['apiserver']['logging']:
    log.setLevel(logging.ERROR)

vars.queue = []
vars.starttime = datetime.now()
vars.webresults = {}
vars.channels = {}
vars.ninadata = {}
vars.ninawarningsposted = []
vars.ninachan = 6
vars.ninacount = 0
vars.ninasenttitlehashes = {}
vars.warnings = ''
vars.banned = []

slowmode = {}
nodes = {}
history_channels = {}

with open("banlist.txt", "r") as f:
    vars.banned = f.readlines()


vars.pullkeys = vars.config['ninawarnings']['regionkeys']
vars.regions = vars.config['ninawarnings']['regionnames']

stats = {
    'packetcount': 0,
    'lastsend': 0,
    'messages_received': 0,
    'messages_sent': 0,
}
vars.connected = False

if vars.config['badwords']['enabled']:
    with open(vars.config['badwords']['file'], 'r') as file:
        vars.badwords = [line.strip() for line in file]



if vars.config['apiserver']['enabled']:
    app = Flask(__name__)

    @app.route('/')
    def api_complete():
        ret = {
            'info': me,
            'stats': stats,
            'history_channels': history_channels
        }

        response = jsonify(ret)

        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "*")
        response.headers.add("Access-Control-Allow-Methods", "*")
        
        return response

    @app.route("/api/send", methods=['GET', 'POST'])
    def api_send():
        data = request.get_json()
        ret = {
            'result': 'none'
        }
        try:
            if data['token'] in vars.config['apiserver']['tokens']:
                vars.log(data)
                sendSplittedText(False,data['message'],int(data['channel']))
                ret = {
                    'result': 'ok'
                }
            else:
                ret = {
                    'result': 'noauth'
                }
        except Exception as e:
            ret = {
                'result': 'error',
                'error': e
            }            
            pass
        response = jsonify(ret)

        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "*")
        response.headers.add("Access-Control-Allow-Methods", "*")
        data = request.get_json()
        return response

def remove_html_tags(text):
    import re
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def has_cyrillic(text):
    import re 
    return bool(re.search('[а-яА-Я]', text))

def censore(text):
    if has_cyrillic(text):
        return "*** SOME CENSORED CYRILLIC TEXT ***"
    
    if not vars.config['badwords']['enabled']:
        return text
    
    import re
    for word in vars.badwords:
        c = re.compile(re.escape(word.lower()), re.IGNORECASE)
        text = c.sub('***', text)
   
    return text

def findRegion(c):
    for r in vars.regions:
        if str(c).startswith(r):
            return vars.regions[r]
    return ""         

def queueSend(type, text, destination):
    try:
        vars.queue.append({
            'type': type,
            'text': text,
            'destination': destination,
        })
    except:
        pass
    pass

def sendSplittedText(ifc, txt, channel):
    if len(vars.queue) + 1 > vars.config['general']['maxqueue']:
        vars.log("** Maximum send queue ** Ignoring a message **")
        
    try:
        txt = remove_html_tags(txt)
        maxlen = vars.config['general']['maxlength']
        if len(txt) <= maxlen:
            stats['messages_sent'] = stats['messages_sent'] + 1
            queueSend('channel', txt, channel)
        else:
            wrapped = textwrap.fill(txt, maxlen)
            parts = wrapped.split("\n")
            p = 0
            for part in parts:
                stats['messages_sent'] = stats['messages_sent'] + 1
                p = p + 1
                s =  part + ' ('+str(p)+'/'+str(len(parts))+')'
                queueSend('channel', s, channel)
    except:
        vars.log("sendSplittedError")

class WebFetcher(threading.Thread):
    def __init__(self, name, url, interval, sleft, sright, prepend, append):
        threading.Thread.__init__(self)
        
        self.name = name
        self.url = url
        self.interval = interval
        self.sleft = sleft
        self.sright = sright
        self.name = name
        self.prepend = prepend
        self.append = append

    def run(self):
        while True: 
            ferr = False  
            try:
                response = requests.get(self.url, timeout=vars.config['general']['fetchtimeout'])
                contents = response.text

                s1 = contents.split(self.sleft,1)
                ret = ''
                if len(s1) == 2:
                    s2 = s1[1].split(self.sright)
                    if len(s2) > 0:
                        ret = self.prepend + s2[0] + self.append
                        ret = ret.replace("\\n", " ")
                        ret = ret.replace("  ", " ")
                        ret = html.unescape(ret)
                        ret = remove_html_tags(ret)
            except:
                ferr = True
                vars.log(self.name + " - Fetch Error")
                ret = ''

            if not self.name in vars.webresults:
                vars.webresults[self.name] = ''

            if ret != '' and ferr == False:
                if ret != vars.webresults[self.name]:
                    if self.name == 'weather':
                        ret = '['+vars.config['weather']['name']+' '+str(datetime.now().strftime("%H:%M"))+' Uhr] ' + ret
                    vars.webresults[self.name] = ret

            time.sleep(self.interval)

class SendTimer(threading.Thread):
    def __init__(self, cron, interface):
        threading.Thread.__init__(self)        
        self.cron = cron
        self.interface = interface

    def run(self):
        while True:
            if str(datetime.now().strftime("%H:%M")) in self.cron:
                c = self.cron[str(datetime.now().strftime("%H:%M"))]
                
                vars.log("Cronjob " + str(datetime.now().strftime("%H:%M")))
                vars.log(c)

                lines = False

                if 'sendwebresult' in c:
                    data = vars.webresults[c['sendwebresult']]
                    if data != '':
                        sendSplittedText(self.interface,data,c['sendchannel'])


                    time.sleep(60)

            time.sleep(3)

class NinaWarner(threading.Thread):
    def __init__(self, interface):
        threading.Thread.__init__(self) 
        self.interface = interface

    def run(self):
        while(True):
            vars.log("=== NINA Warnings ===")
            getNinaWarnings(self.interface, vars.ninachan)
            time.sleep(vars.config['ninawarnings']['fetchinterval'])
        pass

class SendQueue(threading.Thread):
    def __init__(self, interface):
        threading.Thread.__init__(self) 
        self.interface = interface

    def run(self):
        while(True):
            if len(vars.queue) > 0:
                el = vars.queue.pop(0)
                try:
                    if el['type'] == 'dm':
                        vars.log("Sending queued DM")
                        self.interface.sendText(
                            text=el['text'],
                            destinationId=el['destination'],
                            wantAck=False,
                            wantResponse=False
                        ) 
                    else:
                        vars.log("Sending queued Channel Message")
                        vars.log(el)
                        self.interface.sendText(
                            text=el['text'],
                            channelIndex=el['destination'],
                            wantAck=False,
                            wantResponse=False
                        )
                    vars.log("Queue length: " + str(len(vars.queue)))
                    time.sleep(vars.config['general']['senddelay'])
                except:
                    time.sleep(0.5)
                    vars.log("Queue Error!")
                    pass
            else:
                time.sleep(0.5)

def onReceive(packet, interface): 
    buildNodeDB(interface)
    stats['packetcount'] = stats['packetcount'] + 1
    try:
        if 'decoded' in packet and packet['decoded']['portnum'] == 'TEXT_MESSAGE_APP':
            stats['messages_received'] = stats['messages_received'] + 1
            message_bytes = packet['decoded']['payload']
            message_string = message_bytes.decode('utf-8')
            vars.log(">> " + str(message_string))
            if not 'channel' in packet:
                packet['channel'] = 0

            if packet['toId'] != '^all':
                stats['messages_sent'] = stats['messages_sent'] + 1
                queueSend('dm', vars.config['general']['dmresponse'], packet['from'])

            if ((packet['toId'] == '^all') and ('channel' in packet)):
                channel = str(packet['channel'])
                if not channel in history_channels:
                    history_channels[channel] = []
                if not '*' in history_channels:
                    history_channels['*'] = []

                message_bytes = packet['decoded']['payload']
                message_string = message_bytes.decode('utf-8')
                message_string = message_string.strip()
                message_string = censore(message_string)

                messagedata = {
                    'senderid': str(packet['from']),
                    'time': int(time.time()),
                    'timestr': str(datetime.now().strftime("%d.%m.%Y - %H:%M:%S")),
                    'sendername': str(getNodeName(str(packet['from']))),
                    'channelname': str(getChannelName(int(packet['channel']))),
                    'text': str(message_string.strip())
                }
                
                if not packet['channel'] in vars.config['channels']['private']:
                    if not (str(packet['from'])+'\n' in vars.banned):
                        try:
                            history_channels[channel].append(messagedata)
                            history_channels['*'].append(messagedata)
                        except:
                            pass

                        if len(history_channels[channel]) > vars.config['apiserver']['history']:
                            history_channels[channel].pop(0)

                        if len(history_channels['*']) > vars.config['apiserver']['history']:
                            history_channels['*'].pop(0)

                if (str(packet['from']) in vars.config['general']['admins']) and (packet['channel'] == 7):
                    if message_string.lower().startswith('/reboot'):
                        sendSplittedText(interface, '[REBOOTING]', packet['channel'])
                        time.sleep(10)
                        os.system('sudo shutdown -r now')

                    if message_string.lower().startswith('/exit') or message_string.lower().startswith('/quit'):
                        sendSplittedText(interface, '[EXITING]', packet['channel'])    
                        time.sleep(10)
                        os._exit(1)

                isadmin = False
                ignoremessage = False
                isadminchannel = False

                if str(packet['from']) in slowmode:
                    if time.time() - slowmode[str(packet['from'])] < vars.config['general']['throttle']:
                        ignoremessage = True
                        vars.log("Throtteled Message")

                if (str(packet['from'])+'\n' in vars.banned):
                    vars.log("Banned user message")
                    ignoremessage = True

                if (str(packet['from']) in vars.config['general']['admins']):
                    vars.log("Admin-Message (Throttle disabled)")
                    isadmin = True
                    ignoremessage = False

                if (packet['channel'] == vars.config['channels']['admin']):
                    isadminchannel = True

                if ignoremessage == False:
                    if message_string.lower().startswith(vars.config['commands']['echo'].lower() + ' '):
                        if not packet['channel'] in vars.config['channels']['ignore']:
                            slowmode[str(packet['from'])] = time.time()
                            stats['lastsend'] = time.time()
                            d = message_string.split(' ', 1)
                            if len(d) > 1:
                                sendSplittedText(interface, '[ECHO-REPLY] '+d[1].strip(), packet['channel'])
                    
                    if message_string.lower().startswith(vars.config['commands']['ping'].lower()):
                        if not packet['channel'] in vars.config['channels']['ignore']:
                            slowmode[str(packet['from'])] = time.time()
                            stats['lastsend'] = time.time()
                            vars.log("Sending Pong")
                            stattxt = ''
                            try:
                                stattxt += 'Hops: ' + str(packet['hopStart']-packet['hopLimit'])
                                stattxt += ' RSSI: ' + str(packet['rxRssi'])
                                stattxt += ' SNR: ' + str(packet['rxSnr'])
                                if 'viaMqtt' in packet:
                                    stattxt += ' (via MQTT)'
                                else:
                                    stattxt += ' (via LoRa)'
                            except Exception as e:
                                vars.log(e)
                            sendSplittedText(interface, '[PONG at '+str(datetime.now().strftime("%H:%M:%S"))+' to Node: ' + str(getNodeName(str(packet['from']))) + '] ' +stattxt+  '', packet['channel'])

                    if message_string.lower().startswith(vars.config['commands']['info'].lower()):
                        if packet['channel'] in vars.config['channels']['info']:
                            slowmode[str(packet['from'])] = time.time()
                            try:
                                uptime = str(datetime.now() - vars.starttime).split('.', 2)[0]
                            except:
                                uptime = str(datetime.now() - vars.starttime)
                            stats['lastsend'] = time.time()
                            text='Web: '+vars.config['general']['boturl']+'\nGruppe: '+vars.config['general']['groupurl']+'\nBevölk.-Warn.: ' + str(vars.ninacount) +'\nLandkreise: ' + str(len(vars.pullkeys)) + '\nVersion: Nodebot v'+vars.vrsn+'\n/help für Kommandos'
                            
                            sendSplittedText(interface,text,packet['channel'])
                            vars.log("Sending Info")

                    if message_string.lower().startswith(vars.config['commands']['stats'].lower()):
                        if packet['channel'] in vars.config['channels']['info']:
                            slowmode[str(packet['from'])] = time.time()
                            try:
                                uptime = str(datetime.now() - vars.starttime).split('.', 2)[0]
                            except:
                                uptime = str(datetime.now() - vars.starttime)
                            node_info = interface.getMyNodeInfo()

                            
                            stats['lastsend'] = time.time()
                            text='Statistik:\nPackets: '+str(stats['packetcount'])+'\nRX/TX: '+str(stats['messages_received'])+'/'+str(stats['messages_sent'])+'\nUptime: '+uptime+'\nChUtil: ' + str(round(node_info['deviceMetrics']['channelUtilization'],2)) + '%'+'\nAirUtil: ' + str(round(node_info['deviceMetrics']['airUtilTx'],2)) + '%'
                            sendSplittedText(interface,text,packet['channel'])
                            vars.log("Sending Stats")

                    if message_string.lower().startswith(vars.config['commands']['help'].lower()):
                        if packet['channel'] in vars.config['channels']['info']:
                            slowmode[str(packet['from'])] = time.time()
                            stats['lastsend'] = time.time()
                            vars.log("Sending Help")
                            stats['messages_sent'] = stats['messages_sent'] + 1
                            text='[NRW-Info]\n/info\n/help\n/stats\n/ping\n/warnungen\nEinige Kommandos haben einen Cooldown um Spam zu verhindern.'
                            queueSend('channel', text, packet['channel'])
                    
                    if message_string.lower().startswith(vars.config['commands']['warnings'].lower()):
                        if packet['channel'] in vars.config['channels']['info']:
                            if vars.warnings == '':
                                wrng = ' Keine aktiven Warnungen'
                            else:
                                wrng = vars.warnings
                            slowmode[str(packet['from'])] = time.time()
                            stats['lastsend'] = time.time()
                            wrn =  '[NRW-WARN]' + wrng + ' [/ENDE]'
                            sendSplittedText(interface, wrn, packet['channel'])
                            vars.log("Warnings sent.")
                    
                    if isadmin and isadminchannel and message_string.lower().startswith('/debug'):
                        txt="Debug :-)"
                        sendSplittedText(interface,txt,7)

                    if isadmin and isadminchannel and message_string.lower().startswith('/ban '):
                        d = message_string.split(' ', 1)
                        if len(d) > 1:
                            with open('banlist.txt', 'a') as banlist:
                                banlist.write(d[1].strip()+'\n')
                            with open("banlist.txt", "r") as f:
                                vars.banned = f.readlines()
                            sendSplittedText(interface, str(getNodeName(str(d[1].strip()))) + ' was banned from the bot.', packet['channel'])

                    if isadmin and isadminchannel and message_string.lower().startswith('/unban '):
                        d = message_string.split(' ', 1)
                        if len(d) > 1:
                            with open("banlist.txt", "r") as f:
                                lines = f.readlines()
                            with open("banlist.txt", "w") as f:
                                for line in lines:
                                    if line.strip("\n") != d[1].strip():
                                        f.write(line)
                            with open("banlist.txt", "r") as f:
                                vars.banned = f.readlines()
                            sendSplittedText(interface, str(getNodeName(str(d[1].strip()))) + ' was unbanned from the bot.', packet['channel'])

                    if isadmin and isadminchannel and message_string.lower().startswith('/banlist'):
                        with open("banlist.txt", "r") as f:
                            lines = f.readlines()
                        bans = ' '.join(lines)
                        sendSplittedText(interface, 'Banlist: ' + bans.replace('\n',' '), packet['channel'])

                    if isadmin and isadminchannel and message_string.lower().startswith('/weathertest'):
                        slowmode[str(packet['from'])] = time.time()
                        stats['lastsend'] = time.time()
                        sendSplittedText(interface,vars.webresults['weather'],packet['channel'])
                        vars.log("Wetter gesendet.")
                                                
                    if message_string.lower().startswith('moin') or message_string.lower().startswith('hallo') or message_string.lower().startswith('guten tag') or message_string.lower().startswith('tach') or message_string.lower().startswith('nabend') or message_string.lower().startswith('guten abend'):
                        if random.randrange(10) > 7:
                            vars.log("Answering the Greeting")
                            slowmode[str(packet['from'])] = time.time()
                            time.sleep(random.randrange(3)+1)
                            stats['lastsend'] = time.time()
                            greetings=['Moinsen', 'Hi!','hi', 'Tach', 'Moin', 'Mahlzeit', 'Gude', 'moin moin', 'howdy', 'cheers', 'Hallo!']
                            greeting = random.choice (greetings)   
                            stats['messages_sent'] = stats['messages_sent'] + 1                     
                            queueSend('channel', str(greeting), packet['channel'])
                        
                    if message_string.lower().strip()==vars.config['commands']['test'].lower():
                        vars.log(packet)
                        slowmode[str(packet['from'])] = time.time()
                        stats['lastsend'] = time.time()
                        vars.log("Sending Test OK")
                        stattxt = ''
                        try:
                            stattxt += 'Hops: ' + str(packet['hopStart']-packet['hopLimit'])
                            stattxt += ' RSSI: ' + str(packet['rxRssi'])
                            stattxt += ' SNR: ' + str(packet['rxSnr'])
                            if 'viaMqtt' in packet:
                                stattxt += ' (via MQTT)'
                            else:
                                stattxt += ' (via LoRa)'
                        except Exception as e:
                            vars.log(e)

                        stats['messages_sent'] = stats['messages_sent'] + 1
                        text='[Test OK / '+str(datetime.now().strftime("%H:%M:%S"))+' / NodeID#' + str(getNodeName(str(packet['from']))) + '] ' +stattxt+  ''
                        queueSend('channel', text, packet['channel'])
                    vars.log('----------- PARSED ----------')
                else:
                    vars.log('----------- IGNORED DUE TO SPAM DELAY -------------')
    except KeyError as e:
        vars.log(f"Error processing packet: {e}")
    
def onConnection(interface, topic=pub.AUTO_TOPIC): 
    time.sleep(10)
    stats['messages_sent'] = stats['messages_sent'] + 1
    queueSend('channel', '[ONLINE]', vars.config['channels']['admin'])
    vars.log("=== READY ===")
    pass

def onConnectionLost(interface, topic=pub.AUTO_TOPIC): 
    vars.log("Connection lost")
    interface.close()
    vars.connected = False
    while not vars.connected:
        vars.log("Reconnecting...")
        time.sleep(10)
        interface = meshtastic.tcp_interface.TCPInterface(hostname=vars.config['connection']['wifiip'])
    pass

def buildNodeDB(ifc):
    if ifc.nodes:
        for node in ifc.nodes.values():
            try:
                nodes[str(node['num'])] = node
            except:
                pass

def getNodeName(userid):
    userid = str(userid)
    if userid in nodes:
        if nodes[userid]['user']['shortName'] == None:
            return userid
        return nodes[userid]['user']['longName'] + ' ('+ nodes[userid]['user']['shortName']+')'
    else:
        return userid

def getChannelName(index):
    if str(index) in vars.channels:
        return vars.channels[str(index)]
    else:
        return "Unknown Channel"

def getNinaWarnings(ifc,chan):
    try:
        v = vars.ninasenttitlehashes
        for k in v:
            if v[k] < int(time.time()) - 86400:
                vars.ninasenttitlehashes.pop(k)
    except:
        vars.log("Failed deleting Hashes")

    ninacount = 0
    wgn = ''
    senddisclaimer = 0
    try:
        for key in vars.pullkeys:
            region = findRegion(str(key))

            ninareq = requests.get(vars.config['ninawarnings']['dashurljson']+str(key)+'.json', timeout=vars.config['general']['fetchtimeout'])
            if ninareq.status_code == 200:
                warnings = json.loads(ninareq.text)
                if str(key) in vars.ninadata:            
                    vars.ninadata[str(key)] = warnings
                    for warning in vars.ninadata[str(key)]:
                        if not warning['payload']['data']['provider'] == 'DWD':
                            warning['payload']['data']['headline'] = region + ': ' + warning['payload']['data']['headline']

                        if not 'entwarnung' in warning['payload']['data']['headline'].lower() and not 'aufhebung' in warning['payload']['data']['headline'].lower():
                            if not str(hashlib.md5(warning['payload']['data']['headline'].encode()).hexdigest()) in vars.ninasenttitlehashes:
                                ninacount = ninacount + 1
                                wgn = wgn + ' +++ ' + warning['payload']['data']['headline']
                            
                        if not warning['id'] in vars.ninawarningsposted:
                            vars.ninawarningsposted.append(warning['id'])

                            if not str(hashlib.md5(warning['payload']['data']['headline'].encode()).hexdigest()) in vars.ninasenttitlehashes:
                                vars.ninasenttitlehashes[str(hashlib.md5(warning['payload']['data']['headline'].encode()).hexdigest())] = int(time.time())
                                senddisclaimer = True
                                vars.log("Sending the warning")
                                vars.log(warning)
                                txt = '[Katastrophenschutz '+ warning['payload']['data']['provider'] + ']\n'+'' + warning['payload']['data']['headline'] + ' - /info'
                                sendSplittedText(ifc, txt, chan)
                                if not warning['payload']['data']['provider'] == 'DWD':
                                    if not 'entwarnung' in txt.lower():
                                        try:
                                            detailsreq = requests.get(vars.config['ninawarnings']['detailurljson']+warning['id']+'.json', timeout=vars.config['general']['fetchtimeout'])
                                            if detailsreq.status_code == 200:
                                                details = json.loads(detailsreq.text)
                                                desc = '[DETAILS] ' + details['info'][0]['description']
                                                time.sleep(8)
                                                sendSplittedText(ifc, desc + ' (/info für mehr)', chan)
                                            else:
                                                time.sleep(8)
                                                sendSplittedText(ifc, '[DETAILS] Details sind zu dieser Meldung derzeit nicht verfügbar. /info für mehr', chan)
                                        except:
                                            vars.log("Details Fetch Error")
                                            time.sleep(8)
                                            sendSplittedText(ifc, '[DETAILS] Details sind zu dieser Meldung derzeit nicht abrufbar (Fehler). /info für mehr', chan)
                                            pass
                                time.sleep(10)
                else:
                    vars.ninadata[str(key)] = warnings
                    for warning in vars.ninadata[str(key)]:
                        if not warning['payload']['data']['provider'] == 'DWD':
                            warning['payload']['data']['headline'] = region + ': ' + warning['payload']['data']['headline']
                        if not 'entwarnung' in warning['payload']['data']['headline'].lower() and not 'aufhebung' in warning['payload']['data']['headline'].lower():
                            if not str(hashlib.md5(warning['payload']['data']['headline'].encode()).hexdigest()) in vars.ninasenttitlehashes:
                                ninacount = ninacount + 1
                                wgn = wgn + ' +++ ' + warning['payload']['data']['headline']
                        vars.ninawarningsposted.append(warning['id'])
                        vars.ninasenttitlehashes[str(hashlib.md5(warning['payload']['data']['headline'].encode()).hexdigest())] = int(time.time())
        vars.log("Warning-Fetch successful.")
    except Exception as e:
        vars.log("Warning-Fetch failed.")
        vars.log(e)
        pass
    vars.ninacount = ninacount
    vars.warnings = wgn


# Bot Start
if __name__ == '__main__':
    pub.subscribe(onReceive, "meshtastic.receive")
    pub.subscribe(onConnection, "meshtastic.connection.established")
    pub.subscribe(onConnectionLost, "meshtastic.connection.lost")
    vars.log("=== CONNECTION TO NODE ===")
    if vars.config['connection']['wifiip'] == '':
        vars.log('...via Serial')
        interface = meshtastic.serial_interface.SerialInterface()
    else:
        vars.log('...via WiFi')
        interface = meshtastic.tcp_interface.TCPInterface(hostname=vars.config['connection']['wifiip'])
    
    vars.log('=== Build NODES-DB ===')
    buildNodeDB(interface)

    vars.log("=== NODEINFO ===")
    node_info = interface.getMyNodeInfo()
    vars.log(node_info)

    me = {
        'userid': node_info['user']['id'],
        'id': node_info['num'],
        'name': node_info['user']['longName'],
        'short': node_info['user']['shortName'],
    }

    mynode = interface.getNode('^local')
    channels = mynode.channels

    vars.log("=== CHANNELS ===")
    if channels:
        vars.log("Channels:")
        for channel in channels:
            if channel.role:
                psk_base64 = base64.b64encode(channel.settings.psk).decode('utf-8')
                channelname = channel.settings.name
                if channelname == "":
                    channelname = "LongFast"
                vars.channels[str(channel.index)] = channelname
                vars.log(f"Index: {channel.index}, Role: {channel.role}, PSK (Base64): {psk_base64}, Name: {channelname}")
    else:
        vars.log("No channels found.")

    if vars.config['general']['chanexit']:
        vars.log(codecs.encode('> Lbh qvq abg pbasvther gur obg pbeerpgyl. Cyrnfr ernq gur znahny.', 'rot_13'))
        os._exit(1)

    if vars.config['weather']['enabled']:
        weatherfetcher = WebFetcher('weather',vars.config['weather']['url'],vars.config['weather']['fetchinterval'],vars.config['weather']['split_left'],vars.config['weather']['split_right'],'', ' / '+vars.config['weather']['sourcename']+' (/info für mehr)')
        weatherfetcher.start()

    sendtimer = SendTimer(vars.config['cron'], interface)
    sendtimer.start()

    # Nina
    if vars.config['ninawarnings']['enabled']:
        vars.log("=== NINA Fetching region keys ===")
        try:
            localkeysreq= requests.get(vars.config['ninawarnings']['keyurl'], timeout=vars.config['general']['fetchtimeout'])
            if localkeysreq.status_code == 200:
                localkeys = json.loads(localkeysreq.text)
                vars.localkeys = {}
                vars.pullkeys = []
                for localkey in localkeys['daten']:
                    if str(localkey[0]).startswith(vars.config['ninawarnings']['state']):
                        vars.localkeys[str(localkey[0])] = str(localkey[1])
                        pk = str(localkey[0])[:-7] + '0000000'
                        if not pk in vars.pullkeys:
                            vars.pullkeys.append(pk)
            vars.log('Region keys fetched')
        except:
            vars.log('Fetching region keys failed!')
            pass

        ninawarner = NinaWarner(interface)
        ninawarner.start()

    queue = SendQueue(interface)
    queue.start()

    if vars.config['apiserver']['enabled']:
        app.run(host=vars.config['apiserver']['host'],port=vars.config['apiserver']['port'])
        
    while True:
        time.sleep(1000)
