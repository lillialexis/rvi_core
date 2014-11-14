#!/usr/bin/python

#
# Copyright (C) 2014, Jaguar Land Rover
#
# This program is licensed under the terms and conditions of the
# Mozilla Public License, version 2.0.  The full text of the 
# Mozilla Public License is at https://www.mozilla.org/MPL/2.0/
#

#
# GPS Data Collector
# This tool collects data from the gpsd daemon and stores it in the RVI Backend
# database using the Django ORM.
#

import sys
import getopt
import os
import time
import threading
import random 
from signal import *
from gps import *
import json
from rvi_json_rpc_server import RVIJSONRPCServer
import jsonrpclib
import sqlite3


MY_NAME = "GPS Collector"

class Logger:
    def __init__(self, db_file = /var/tmp/big_data_demo.sql):
        self.dbc = sqlite3.connect(db_file)
        self.subscriptions = {}

        # Create the table that stores log data and index it on its timestamps
        self.dbc.execute('''CREATE TABLE IF NOT EXISTS log (timestamp, channel, value)''')
        self.dbc.execute('''CREATE INDEX IF NOT EXISTS ts_index on log (timestamp)''')

        # Create a table to store all our subscriptions so that they survive a 
        # system restert.
        self.dbc.execute('''CREATE TABLE IF NOT EXISTS subscription (channel, interval)''')

        # Retrieve all our subscriptions so that they are easily accessible
        for subscription in c.execute('''SELECT channel, interval FROM subscription'''):
            (channel, interval) = subscription
            # Interval is the sample interval in sec. 
            # 0 is when the UTC of when last sample was made.
            self.subscriptions['channel'] = ( interval, 0 )
            

    def add_subsciption(channel, sample_interval):
        if not channel in self.subscriptions:
            # Setup a new channel in the dictionary
            self.subscriptions(channel) = (sample_interval, 0)
            self.dbc.execute('''INSERT INTO subscriptions (?, ?)''', channel, sample_interval)

    def delete_subsciption(channel):
        if channel in self.subscriptions:
            # Remove from subscriptions
            self.subscriptions.del(channel)
            self.dbc.execute('''DELETE FROM subscriptions WHERE channel=?''', channel)


    def add_sample(channel, value):
        # If the channel is not among our subscriptions, then ignore.
        if not channel in self.subscriptions:
            return False

        # If it is not time for us to sample the given channel yet, then ignore
        
        self.dbc.execute('''INSERT INTO  (?, ?)''', channel, sample_interval)
        
    

    
class GPSPoller(threading.Thread):
    
    def __init__(self):
        threading.Thread.__init__(self)
        self.session = gps(mode=WATCH_ENABLE)
        
    def shutdown(self):
        self._Thread__stop()
        
    def run(self):
        while True:
            self.session.next()


class GPSCollector:
    """
    """
    
    def __init__(self, destination,vin, interval, nofix=False):
        self.vin = vin
        self.interval = interval
        self.nofix = nofix
        self.last_speed = 1.0
        self.gps_poller = GPSPoller()
        self.destination = destination
        self.transaction_id = 1
    def run(self):
        # start GPS polling thread
        self.gps_poller.start()

        # catch signals for proper shutdown
        for sig in (SIGABRT, SIGTERM, SIGINT):
            signal(sig, self.cleanup)

        # main execution loop
        while True:
            try:
                time.sleep(self.interval)
                
                # process GPS data
                session = self.gps_poller.session
                print session
                if (session.status == MODE_NO_FIX) and not self.nofix:
                    print "Waiting for GPS to fix..."
                    continue

                #time = session.utc
                # location.loc_latitude = session.fix.latitude
                #location.loc_longitude = session.fix.longitude
                #location.loc_altitude = session.fix.altitude
                #location.loc_speed = session.fix.speed
                #location.loc_climb = session.fix.climb
                #location.loc_track = session.fix.track
                
                if not isnan(session.fix.time):
                    if (session.fix.speed < 0.1) and (self.last_speed < 0.1):
                        print "Waiting for speed..."
                        # continue

                    self.last_speed = session.fix.speed
                    # if the time is valid the data record is valid

                    print "Location:", session
                    rvi_server.message(calling_service = "/big_data",
                                   service_name = self.destination + "/logging/report",
                                   transaction_id = self.transaction_id,
                                   timeout = int(time.time())+60,
                                   parameters = [{ 
                                       u'vin': self.vin,
                                       u'timestamp': session.utc,
                                       u'data': [
                                           {  u'channel': 'waypoint', 
                                              u'value': { 
                                                  u'lat': session.fix.latitude,
                                                  u'lon': session.fix.longitude,
                                                  u'alt': session.fix.altitude
                                              }
                                          }
                                       ]
                                   }])
                    self.transaction_id += 1

                else:
                    print "Invalid location:", session
                    

            except KeyboardInterrupt:
                print ('\n')
                break
            

    def cleanup(self, *args):
        logger.info('%s: Caught signal: %d. Shutting down...', MY_NAME, args[0])
        if self.gps_poller:
            self.gps_poller.shutdown()
        sys.exit(0)

def subscribe(channels, interval):
    print "subscribe(): channels:", channels
    print "subscribe(): interval:", interval
    return {u'status': 0}


def unsubscribe(channels):
    print "unsubscribe(): channels:", channels
    return {u'status': 0}


def usage():
    print "Usage: %s RVI-URL VIN" % sys.argv[0]
    sys.exit(255)
        
if __name__ == "__main__":
    #
    # Setup a localhost URL, using a random port, that we will listen to
    # incoming JSON-RPC publish calls on, delivered by our RVI service
    # edge (specified by rvi_url).
    #
    service_host = 'localhost'
    service_port = random.randint(20001, 59999)
    service_url = 'http://'+service_host + ':' + str(service_port)

    # 
    # Check that we have the correct arguments
    #
    if len(sys.argv) != 3:
        usage()

    # Grab the URL to use
    [ progname, rvi_url, vin ] = sys.argv   


    # Setup an outbound JSON-RPC connection to the RVI Service Edeg.
    rvi_server = jsonrpclib.Server(rvi_url)

    service = RVIJSONRPCServer(addr=((service_host, service_port)), logRequests=False)

    #
    # Regsiter callbacks for incoming JSON-RPC calls delivered to
    # this program
    #
        
    service.register_function(subscribe, "/logging/subscribe" )
    service.register_function(unsubscribe, "/logging/unsubscribe" )

    # Create a thread to handle incoming stuff so that we can do input
    # in order to get new values
    thr = threading.Thread(target=service.serve_forever)
    thr.start()


    # We may see traffic immediately from the RVI node when
    # we register. Let's sleep for a bit to allow the emulator service
    # thread to get up to speed.
    time.sleep(0.5)

    #
    # Register our HVAC emulator service with the vehicle RVI node's Service Edge.
    # We register both services using our own URL as a callback.
    #

    # Repeat registration until we succeeed
    rvi_dead = True
    while rvi_dead:
        try: 
            res = rvi_server.register_service(service = "/logging/subscribe",
                                              network_address = service_url)
            rvi_dead = False
        except:
            print "No rvi. Wait and retry"
            time.sleep(2.0)


    full_subscribe_name = res['service']

    res = rvi_server.register_service(service = "/logging/unsubscribe", network_address = service_url)
    full_unsubscribe_name = res['service']

    print "HVAC Emulator."
    print "Vehicle RVI node URL:       ", rvi_url
    print "Emulator URL:               ", service_url
    print "Full subscribe service name :  ", full_subscribe_name
    print "Full unsubscribe service name  :  ", full_unsubscribe_name

    interval = 100
    gps_collector = None
    nofix = False

    gps_collector = GPSCollector("jlr.com/backend", vin, interval, nofix)

    # Let the main thread run the gps collector

    gps_collector.run()
            


