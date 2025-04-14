nbvar = 0
vrsn = '1.1b'

def clearlog():
    with open('./nodelog.txt', 'w') as logfile:
        logfile.write(str('STARTLOG'))

def log(txt):
    print(txt)
    with open('./nodelog.txt', 'a') as logfile:
        logfile.write(str(txt) + '\n')
