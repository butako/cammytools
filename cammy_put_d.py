#!/usr/bin/python

import sys
import os.path
import os
import time
import traceback
import logging
import logging.handlers
import argparse
from ftplib import FTP
import ftplib
from PIL import Image
import subprocess
import tempfile
import shutil

FTPH = None

def archive_cleanup(archivedir, archivedays):
	logging.info("Cleaning from archive {} days {}...".format(archivedir, archivedays))
	day_dirs = sorted(os.listdir(archivedir), reverse = True)
	for day_dir in day_dirs[archivedays:]:
		logging.info("Removing {}".format(day_dir))
		shutil.rmtree(os.path.join(archivedir, day_dir), True)
	logging.info("Cleaning of archive done.")

def archive_images2(imagedir, archivedir, archivedays):
	archive_cleanup(archivedir, archivedays)
	logging.info("Archiving images...")
	for fname in get_files(imagedir):
		# split apart the image filename into pieces. The filename from motion
		# is formatted: 20151117_211520_01
		# and the target folder structure will be YYYYMMDD/HH/file.jpg
		if not fname.endswith('jpg') or fname.endswith('_sml.jpg'):
			logging.debug("Skipping archive of file {}, not recognized".format(fname))
			continue

		yyyymmdd = fname.split('_')[0]
		hh = fname.split('_')[1][:2]

		target = os.path.join(archivedir, yyyymmdd, hh)
		logging.info("Archiving {} to {}".format(fname, target))

		if os.path.isfile(os.path.join(target,fname)):
			logging.warning("File {} already exists in {} during archiving.".format(fname, target))
		else:
			if not os.path.isdir(target):
				os.makedirs(target)
			shutil.copy(os.path.join(imagedir, fname), target)

	logging.info("Archiving images done.")


def archive_timelapse_video(imagedir, archivedir):
	logging.info("Archiving timelapse...")
	for fname in get_files(imagedir, 'AVI'):
		
		i = int( time.time() - os.path.getmtime(os.path.join(imagedir, fname)))
		if (i < 60):
			logging.debug("Skipping archive of file {}, it has recently been modified.".format(fname))
			continue

		yyyymmdd = fname.split('_')[0]
		hh = fname.split('_')[1][:2]

		target = os.path.join(archivedir, yyyymmdd, hh)
		logging.info("Archiving {} to {}".format(fname, target))

		if os.path.isfile(os.path.join(target,fname)):
			logging.warning("File {} already exists in {} during archiving.".format(fname, target))
		else:
			if not os.path.isdir(target):
				os.makedirs(target)
			shutil.copy(os.path.join(imagedir, fname), target)
		# remove avi files during archive. Image files are removed only after FTP upload was success.
		remove_file(imagedir, fname)

		
	logging.info("Archiving timelapse done.")

def resize_image(imagedir, imagefname, targetfile):
	infile = os.path.join(imagedir, imagefname)
	im = Image.open(infile)
	im.thumbnail( (2000,720) )
	im.save(targetfile, "JPEG", quality = 60)
	logging.info('Resizing {} to {}'.format(infile, targetfile.name))

def get_files(image_dir, extension = 'JPG'):
	fnames = sorted([f for f in os.listdir(image_dir) if f.upper().endswith(extension)])
	return fnames

def ftp_callback(block):
	logging.debug('Sent block...')

def get_ftphandle(username, password):
	global FTPH
	if not FTPH:
		logging.info('Connecting to FTP server.')
		FTPH = FTP(timeout=60)
		FTPH.set_debuglevel(0) # https://docs.python.org/2/library/ftplib.html#ftplib.FTP.set_debuglevel
		FTPH.connect('ftp.cammy.com',10021)
		FTPH.login(username, password)
	return FTPH

def close_ftphandle():
	global FTPH
	try:
		if FTPH:
			FTPH.quit()
	except ftplib.all_errors as e:
		logging.exception('Exception during closing the FTP handle')
	FTPH = None

def ftp_put(ftph, imagedir, imagefile):
	sent = False
	try:
		imagefname = os.path.join(imagedir, imagefile)
		logging.info("FTP STOR {}".format(imagefname))
		resp = ftph.storbinary("STOR " + imagefile, open(imagefname,'rb'), blocksize = 4096, callback = ftp_callback)
		ftph.voidcmd('NOOP')
		logging.info("FTP STOR response code {}".format(resp))
		sent = True
	except ftplib.all_errors as e:
		logging.exception('Exception during putting image')
	except Exception as e:
		logging.exception('Unexpected exception during putting image')
	return sent

def remove_file(imagedir, fname):
	f = os.path.join(imagedir, fname)
	if os.path.isfile(f):
		logging.info("Removing {}".format(f))
		os.remove(f)
		
def get_fileage(imagedir, fname):
	try:
		i = int( time.time() - os.path.getctime(os.path.join(imagedir,fname)) )
	except Exception as e:
		i = 0 
	return i

def ftp_putall(imagedir, username, password, delete, archivedir, archivedays, resize):

	uploaded = False
	up_count = 0
	while True and delete:
		fnames = get_files(imagedir)
		logging.info('^^^ Processing {}, number of images = {}'.format(imagedir, len(fnames)))
		if len(fnames) == 0:
			break

		if archivedir:
			archive_images2(imagedir, archivedir, archivedays)
			archive_timelapse_video(imagedir, archivedir)
			
		i = 0
		retrycount = 0

		for i in range(len(fnames)):
			fname = fnames[i]

			if fname.endswith('_sml.jpg'):
				continue

			logging.info("Putting image {}, {} of {}".format(fname, i, len(fnames)))

			if get_fileage(imagedir, fname) > (60*30) and delete:
				logging.warning("Frame drop! Dropping {}".format(fname))
				remove_file(imagedir, fname)
				continue


			orig_fname = fname
			tmpfile = tempfile.NamedTemporaryFile()
			if resize:
				resize_image(imagedir, fname, tmpfile)
				fname = tmpfile.name

			uploaded = False
			retrycount = 0
			while not uploaded and retrycount < 10:
				ftph = get_ftphandle(username, password)
				uploaded = ftp_put(ftph, imagedir, fname)
				if not uploaded:
					logging.info('Problem during storing {}, retrying'.format(fname))
					close_ftphandle()
					retrycount += 1
				else:
					up_count += 1

			if delete:
				remove_file(imagedir, orig_fname)
			
	close_ftphandle()
	logging.info('@@@ Finished processing {}. Uploaded {} images.'.format(imagedir, up_count))

	return uploaded	
	
	

def main():

	parser = argparse.ArgumentParser(description='Cammy FTP Uploader.')
	parser.add_argument('-u', dest='username', required=True, help='Cammy FTP username')
	parser.add_argument('-p', dest='password', required=True, help='Cammy FTP password')
	parser.add_argument('--log', help='Log file path', default='cammyput.log')
	parser.add_argument('--imagedir', help='Path to images', default='images')
	parser.add_argument('--delete', help='Delete images after uploading', action='store_true', default=False)
	parser.add_argument('--resize', help='Resize images before sending to cammy', action='store_true', default=False)
	parser.add_argument('--archivedir', help='Archive directory', default=None)
	parser.add_argument('--archivedays', help='Number of days of history to keep in archive', default=10)
	parser.add_argument('--cameras', help='List of camera subdirs, e.g. 01 02 03', nargs='+', required=True)

	args = parser.parse_args()

	logFormatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
	rootLogger = logging.getLogger()
	fileHandler = logging.handlers.RotatingFileHandler(args.log, maxBytes=(1048576*5), backupCount=7)
	fileHandler.setFormatter(logFormatter)
	rootLogger.addHandler(fileHandler)

	consoleHandler = logging.StreamHandler(sys.stdout)
	consoleHandler.setFormatter(logFormatter)
	rootLogger.addHandler(consoleHandler)

	rootLogger.setLevel(logging.DEBUG)

	logging.info('CammyPut2 started.')


	while True:
		for camera in args.cameras:
			logging.info('Scanning camera {}...'.format(camera))
			cam_imagedir = os.path.join(args.imagedir, camera)
			cam_archivedir = os.path.join(args.archivedir, camera)

			uploaded = ftp_putall(cam_imagedir, args.username, args.password, args.delete, cam_archivedir, \
						args.archivedays, args.resize)

			if uploaded:
				# pause for cammy to think theres a new event
				time.sleep(60)

		time.sleep(1)




	logging.info("Finished")


if __name__ == '__main__':
	try:
		main()
	except KeyboardInterrupt as e:
		traceback.print_exc()
	except Exception as e:
		traceback.print_exc()
