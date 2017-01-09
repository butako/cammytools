#!/usr/bin/python

import sys
import os.path
import os
import time
import fcntl
import traceback
import logging
import logging.handlers
import argparse
import shutil
from datetime import datetime
from urllib2 import Request, urlopen, URLError

def unix_time(dt):
    epoch = datetime.utcfromtimestamp(0)
    return (dt - epoch).total_seconds() 

def check_for_cat(catcam, camera, catmon, catmac, catlogdir, filename):
    logging.debug('Checking for cat: camera={}; catcam={}; catmon={}; filename={}'.format(camera, catcam, catmon, filename))

    if not catmac or not catmon or catcam != camera:
        return
    yyyymmdd = filename.split('_')[2]
    hhmmss = filename.split('_')[3][:6]

    ts = '{}{}'.format(yyyymmdd, hhmmss)
    #http://rpi:8080/?mac=e3:e2:e9:74:22:4b&when=20161101221000&threshold=-85&period=120

    url = "http://{}/?mac={}&when={}&threshold=-90&period=2".format(catmon, catmac.lower(), ts)

    req = Request(url)
    try:
        response = urlopen(req)
        data = response.readlines()
        logging.debug('Cat check returns {} '.format(data))
        if len(data) > 1 and catlogdir:
            try:
                logging.info('Cat detected! Copying movie from {} to {}'.format(filename, catlogdir))
                shutil.copy2(filename, catlogdir)
            except Exception as e:
                traceback.print_exc()

    except URLError as e:
        if hasattr(e, 'reason'):
            print 'We failed to reach a server.'
            print 'Reason: ', e.reason
        elif hasattr(e, 'code'):
            print 'The server couldn\'t fulfill the request.'
            print 'Error code: ', e.code





def cleanup(target, days, dryrun = False):
    logging.info("Cleaning old movies, days to keep {}...".format(days))
    cameras = os.listdir(target)
    for camera in cameras:
        logging.info("Cleanup of camera {}".format(camera))
        day_dirs = sorted(os.listdir(os.path.join(target, camera, 'record')), reverse = True)
        for day_dir in day_dirs[days:]:
            logging.info("Removing {}".format(day_dir))
            if dryrun:
                logging.info('DRY-RUN. Skipped.')
            else:
                shutil.rmtree(os.path.join(target, camera, 'record', day_dir), True)
    logging.info("Cleaning done.")

def organize(target, dryrun = False, catcam = None, catmon = None, catmac = None, catlogdir = None):
    # Foscam writes into the root FTP directory as follows:
    # <camera_id>/record/[S|M]Dalarm_YYYYMMDD_HHMMSS.mkv
    # What we want to do, is move those files into directories:
    # <camera_id>/record/YYYYMMDD/HH/[S|M]Dalarm_YYYYMMDD_HHMMSS.mkv

    cameras = os.listdir(target)
    for camera in cameras:
        logging.info("Processing camera {}".format(camera))
        movies = os.listdir(os.path.join(target, camera, 'record'))
        for movie in movies:
            if not movie[1:].startswith('Dalarm_'):
                continue
            logging.info("Processing movie {}".format(movie))
            movie_full_fname = os.path.join(target, camera, 'record', movie)
            yyyymmdd = movie.split('_')[1]
            hh = movie.split('_')[2 ][:2]

            check_for_cat(catcam, camera, catmon, catmac, catlogdir, movie_full_fname)

            new_dir = os.path.join(target, camera, 'record', yyyymmdd, hh)
            logging.info("Moving file {} to {}".format(movie, new_dir))
            if not os.path.isdir(new_dir):
                if dryrun:
                    logging.info("DRY-RUN. Make directory skipped")
                else:
                    os.makedirs(new_dir)
            if dryrun:
                logging.info("DRY-RUN. Moving file skipped.")
            else:
                try:
                    shutil.move(movie_full_fname, new_dir)
                except Exception as e:
        			traceback.print_exc()





def main():

    parser = argparse.ArgumentParser(description='Foscam FTP store - movie file organizer')
    parser.add_argument('--log', help='Log file', default='organizer.log')
    parser.add_argument('--target', help='Path to target FTP root directory to organize', default='ftp')
    parser.add_argument('--dryrun', help='Just print, do nothing', action='store_true', default=False)
    parser.add_argument('--keep_days', help='Number of days of history to keep in archive', default=10,
                        type = int)
    parser.add_argument('--catmon', help='Host:port of the cat monitor', default='rpi:8080')
    parser.add_argument('--catcam', help='Identifier of the catcam', default=None)
    parser.add_argument('--catmac', help='Cat Mac Address', default=None)
    parser.add_argument('--catlogdir', help='Path to copy video file for cat log', default='/tmp')



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

    logging.info('Foscam organizer started.')
    organize(args.target, args.dryrun, args.catcam, args.catmon, args.catmac, args.catlogdir)
    cleanup(args.target, args.keep_days, args.dryrun)
    logging.info('Foscam organizer finished.')



if __name__ == '__main__':
	try:
		main()
	except KeyboardInterrupt as e:
		traceback.print_exc()
	except Exception as e:
		traceback.print_exc()
