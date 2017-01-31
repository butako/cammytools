#!/usr/bin/python

import RPi.GPIO as GPIO
import traceback
import sys
import time
import urllib, urllib2
import smtplib
from os.path import basename
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
import logging
import logging.handlers
from collections import deque
import os
import itertools
import argparse
import threading

IMAGES = deque()
ARGS = None
DEBOUNCE_TIMER = None



def send_mail(send_from, send_to, subject, text, files=None,
              server="127.0.0.1"):
    assert isinstance(send_to, list)

    msg = MIMEMultipart()
    msg['From'] = send_from
    msg['To'] = COMMASPACE.join(send_to)
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = subject

    msg.attach(MIMEText(text))

    for f in files or []:
        with open(f, "rb") as fil:
            part = MIMEApplication(
                fil.read(),
                Name=basename(f)
            )
            part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f)
            msg.attach(part)


    smtp = smtplib.SMTP(server)
    smtp.sendmail(send_from, send_to, msg.as_string())
    smtp.close()


def takePhoto():
	logging.debug("Taking photo...")
	before = datetime.now()
	timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
	filename = os.path.join(ARGS.output,"catflap_{}.jpg".format(timestamp))
	url = "http://garagecam.localnet:88/cgi-bin/CGIProxy.fcgi?cmd=snapPicture2&usr={}&pwd={}"\
			.format(ARGS.username, ARGS.password)
	(filename, headers) = urllib.urlretrieve(url, filename)
	after = datetime.now()
	delta = after - before
	logging.info("Photo taken in {} seconds, {} ".format(delta.total_seconds(), filename))
	global IMAGES
	IMAGES.appendleft(filename)
	if len(IMAGES) >= 50:
		r = IMAGES.pop()
		try:
			os.unlink(r)
		except:
			pass
	logging.debug("Images: {}".format(IMAGES))

def takePhoto2(catcam):
	logging.debug("Taking photo...")
	before = datetime.now()
	b = catcam.readline()
	if not b.startswith('--'):
		logging.error("Expected boundary string, got {}".format(b))
		return False
	ct = catcam.readline()
	cls = catcam.readline()
	if not cls.startswith('Content-Length'):
		logging.error("Expected content length, got {}".format(cls))
		return False

	cl = [int(s) for s in cls.split() if s.isdigit()][0]
	catcam.readline()
	imgdata = catcam.read(cl)
	# read newline after data, leaving us ready for next boundary line :
	catcam.readline() 

	timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
	filename = os.path.join(ARGS.output,"catflap_{}.jpg".format(timestamp))

	with open(filename,'wb') as imgfile:
		imgfile.write(imgdata)

	global IMAGES
	IMAGES.appendleft(filename)
	if len(IMAGES) >= 50:
		r = IMAGES.pop()
		try:
			os.unlink(r)
		except:
			pass

	after = datetime.now()
	delta = after - before
	logging.info("Photo taken in {} seconds, {} ".format(delta.total_seconds(), filename))
	return True


def onCatFlapTriggered():
	global IMAGES
	logging.info("Cat flap actually triggered...")
	imgs = list(itertools.islice(IMAGES, 0, 10))
	logging.info("Sending photos: {}".format(imgs))
	timestamp = datetime.now().strftime('%H:%M:%S')
	subject = "{} {}".format("ROSIE Alert", timestamp)

	send_mail(ARGS.mail_from, ARGS.mail_to, 
			subject, 'Cat flap triggered',
			imgs, ARGS.mail_smtp)


def onCatFlapTriggered_debouncer(channel):
	logging.info("Cat flap triggered!")
	global DEBOUNCE_TIMER
	if DEBOUNCE_TIMER:
		logging.info("Bounce debounced.")
		DEBOUNCE_TIMER.cancel()
	
	DEBOUNCE_TIMER = threading.Timer(5, onCatFlapTriggered)
	DEBOUNCE_TIMER.start()

def main(): 
	global IMAGES, ARGS
	parser = argparse.ArgumentParser(description='Cheshire cat capture')
	parser.add_argument('--log', help='Log file path', default='cheshire.log')
	parser.add_argument('--username', help='Camera username', required = True)
	parser.add_argument('--password', help='Camera password', required = True)
	parser.add_argument('--mail_from', help='Source mail address', required = True)
	parser.add_argument('--mail_to', help='Target mail address', default=None, nargs='*', required = True)
	parser.add_argument('--mail_smtp', help='SMTP server', required = True)
	parser.add_argument('--output', help='Path to write images to', default = '.')


	ARGS = parser.parse_args()
	logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
	rootLogger = logging.getLogger()
	fileHandler = logging.handlers.RotatingFileHandler(ARGS.log, maxBytes=(1024*1024*5), backupCount=5)
	fileHandler.setFormatter(logFormatter)
	rootLogger.addHandler(fileHandler)

	consoleHandler = logging.StreamHandler(sys.stdout)
	consoleHandler.setFormatter(logFormatter)
	rootLogger.addHandler(consoleHandler)

	rootLogger.setLevel(logging.INFO)
	GPIO.setmode(GPIO.BCM)

	catFlapChannel = 21
	GPIO.setup(catFlapChannel, GPIO.IN)

	GPIO.add_event_detect(catFlapChannel, GPIO.FALLING, callback=onCatFlapTriggered_debouncer, bouncetime=300)
	

	logging.info( "Cheshire Cat Flap Camera started. Monitoring...")
	fps = 2

	catcam = urllib2.urlopen('http://db:8084/')

	while True:
		#Loop
		before = datetime.now()
		if not takePhoto2(catcam):
			logging.error("Failed to retrieve image from camera. Not multipart?")
			break
		duration = (before - datetime.now()).total_seconds()
		s = max(0, (1 / fps) - duration)
		logging.info("Waiting for {} ".format(s))
		time.sleep(s)

	catcam.close()






if __name__ == '__main__':
	try:
		main()
	except KeyboardInterrupt as e:
		traceback.print_exc()
	except Exception as e:
		traceback.print_exc()     
	sys.exit(0)    

