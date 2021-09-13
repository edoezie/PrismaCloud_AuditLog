# Python script to incrementally read out Prisma Cloud Audit logging and stitch them together in one logfile
# All customer related configuration is maintained in file [config.ini]
# Written by Eric Doezie, Palo Alto 2021
from __future__ import print_function
import json
import requests
import os.path
import configparser
from math import ceil
from requests import api
from datetime import datetime

# Parser config file for mandatory variables - global var
config = configparser.ConfigParser() 

# Function to parse the config.ini file and see if all is OK.
def validateConfigParser():
    try:
        config.read('config.ini')
    except configparser.Error as e:
        raise SystemExit('!!! Error parsing config.ini file!\n %s' % e)
    return

# Function to execute a call to Prisma Cloud. Returns json body of Prisma Cloud's response.
def doPrismaAPICall (APIType, APIEndpoint, APIHeaders, APIData = "", APIParams = ""):
    PRISMA_CLOUD_API_URL = config.get('URL','URL')
    full_URL = PRISMA_CLOUD_API_URL + APIEndpoint
    try:
        response_raw = requests.request(APIType, full_URL, headers=APIHeaders, data=APIData, params=APIParams)
    except requests.exceptions.RequestException as e:
        raise SystemExit('!!! Error doing API call to Prisma Cloud!\n %s' % e)
    if (response_raw.status_code != 200):
        print("!!! API Call returned not-OK! Exiting script.")
        exit(-1)
    return response_raw.json()

# Function to authenticate to Prisma Cloud. Returns token as obtained.
def authenticatePrismaCloud ():
    print("\n--- Authenticating to Prisma Cloud via provided token.")
    api_headers = {'Content-Type': 'application/json'}
    api_endpoint = "/login"
    api_data = {}
    api_data['username'] = config.get('AUTHENTICATION','ACCESS_KEY_ID')
    api_data['password'] = config.get('AUTHENTICATION','SECRET_KEY')
    data_json = json.dumps(api_data)
    response = doPrismaAPICall("POST", api_endpoint, api_headers, data_json, "")
    return response['token']

# Function to open metadata file holding latest successfully ingested entry. If this is the
# first run, will create a new file with 0 as only line.
def readInfoFile ():
    INFO_FILE = config.get('FILES','INFO_FILE')
    last_timestamp = 0
    print("\n--- Processing config file.")

    if (not os.path.isfile(INFO_FILE)):
        print (f" -> Creating new config file [{INFO_FILE}].")
        try:
            f_info = open(INFO_FILE, "w+")
            f_info.write("0\n")
            f_info.close()
            return 0
        except IOError as e:
            raise SystemExit(e)
    print (f" -> Config file [{INFO_FILE}] found.")
    try:
        f_info = open(INFO_FILE, "r")
        last_timestamp = int(f_info.readline())
        f_info.close()
    except IOError as e:
        raise SystemExit(e)
    return last_timestamp

# Function to calculate the difference in seconds between current time and the last saved timestamp
def calculateTimeDifference (timestamp):
    current_time = int(datetime.now().timestamp())
    #last_timestamp_hr = datetime.fromtimestamp(timestamp/1000).strftime('%c')
    current_time_hr = datetime.fromtimestamp(current_time).strftime('%c')
    diff_time = int((current_time) - (timestamp/1000))
    if (diff_time <= 0):
        print ("!!! Timestamp mismatch in config file! Exiting script.")
        exit(-1)
    else:
        #print (f" -> Last timestamp read in: {last_timestamp_hr} [{timestamp}]msec.")
        print (f" -> Current time is {current_time_hr} and difference needing to be ingested is {diff_time} seconds.")
    return diff_time

# Function to calculate the parameters for the API call to audit log endpoint
# Returns amount, time unit and if this is a maximum ingestion
def calculateIngestionNeeded (diff_time):
    MAX_RETRIEVE_HOURS = int(config.get('RETRIEVAL','MAX_RETRIEVE_HOURS'))
    mins_diff = diff_time/60
    hours_diff = diff_time/3600

    print (f"\n--- Analyzing differential time. {diff_time} seconds to be ingested.")
    if  hours_diff >= MAX_RETRIEVE_HOURS:
        print(f" -> Maximum timewindow set for retrieval.")
        return [MAX_RETRIEVE_HOURS, "hour", True]
    if (hours_diff > 1):
        return [ceil(hours_diff), "hour", False]
    else:
        return [ceil(mins_diff), "minute", False]

# Function that queries the audit API endpoint to fetch logs for a certain amount of time
def fetchPrismaAuditLogs(time_amount, time_unit, token):
    action = "GET"
    endpoint =  "/audit/redlock"
    headers = {'x-redlock-auth':token}
    querystring = {"timeType":"relative","timeAmount":time_amount,"timeUnit":time_unit}
    response_raw = doPrismaAPICall(action, endpoint, headers, "", querystring)
    return response_raw

# Function to show analysis on ingested data. Noteworthy: audit entry timestamps from Prisma Cloud API are in msec!
def analyzeIngestedEvents(response_data):
    total_results = len(response_data)
    latest_event_time = oldest_event_time = int(response_data[0]['timestamp'])
    if (total_results > 1): oldest_event_time = int(response_data[total_results - 1]['timestamp'])

    current_time = int(datetime.now().timestamp())
    timestamp_oldest = datetime.fromtimestamp(oldest_event_time/1000).strftime('%c')
    timestamp_latest = datetime.fromtimestamp(latest_event_time/1000).strftime('%c')
    timestamp_current = datetime.fromtimestamp(current_time).strftime('%c')

    print ("\n--- Ingestion cycle starting.")
    print (f" -> Current {current_time}, oldest {oldest_event_time} and latest {latest_event_time} timestamp.")
    print (f" -> Current [{timestamp_current}], oldest [{timestamp_oldest}] and latest [{timestamp_latest}] time.")
    print (f" -> Total results found in timeframe: {total_results}.")
    return

# Function that will open log file holding all entries (append mode), create if non-existent
def mergeLogFile(api_response, last_timestamp, write_data = False):
    DATA_FILE = config.get('FILES','DATA_FILE')
    INFO_FILE = config.get('FILES','INFO_FILE')
    entries_written = 0
    latest_event_time = int(api_response[0]['timestamp'])
    try:
        f_data=open(DATA_FILE, "a+")
        for audit_entry in reversed(api_response):
            timestamp = int(audit_entry['timestamp'])
            if (write_data):
                timestamp_hr = datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d %H:%M:%S')
                f_data.write(f"{timestamp_hr},{audit_entry['user']},{audit_entry['ipAddress']},{audit_entry['resourceType']},{audit_entry['action']},{audit_entry['result']}\n")
                entries_written += 1
            if (timestamp == last_timestamp):
                print(f" -> Last logged timestamp found: {last_timestamp}! Appending enabled.")
                write_data = True
        f_data.close()
    except IOError as e:
        raise SystemExit(e)

    if (not write_data):
        print ("!!! No appending has happened, previous timestamp not found in time window as specified!\n")
    else:
        try:
            f_info = open(INFO_FILE, "w+")
            f_info.write(f"{latest_event_time}\n")
            f_info.close()
            print(f" -> Total entries appended to log file: {entries_written}.\n")
        except IOError as e:
            raise SystemExit(e)

def main ():
    auth_token = ""
    last_processed = 0
    seconds_to_ingest = 0
    ingestion_needed = [0,"hour", False]
    fetched_auditlogs = ""

    validateConfigParser()
    last_processed = readInfoFile()
    seconds_to_ingest = calculateTimeDifference(last_processed)
    ingestion_needed = calculateIngestionNeeded(seconds_to_ingest)
    
    print(f" -> Ingesting {ingestion_needed[0]} {ingestion_needed[1]}s of data.")
    auth_token = authenticatePrismaCloud()
    fetched_auditlogs = fetchPrismaAuditLogs(ingestion_needed[0], ingestion_needed[1], auth_token)
    analyzeIngestedEvents(fetched_auditlogs)
    mergeLogFile(fetched_auditlogs, last_processed, ingestion_needed[2])

if __name__ == "__main__":
    main()