# Prisma Cloud Auditlog Fetch

Version: *1.0*
Author: *Eric Doezie*

### Summary
Python script to incrementally read out Prisma Cloud Audit logging and stitch them together in one logfile

### Requirements and Dependencies

1. Python 3.x or newer

2. Requests (Python library)

```sudo pip install requests```

3. Configparser (Python library)

```sudo pip install configparser```

### Configuration

1. Set all environment variables in the config.ini file
```
All lines in this file are interpreted literally, no escaping required. Data fields are:

[URL]
URL for your Prisma Cloud tenant (example: URL = https://api2.eu.prismacloud.io)

[AUTHENTICATION]
Access and Secret key. These can be obtained from the UI [Prisma Cloud, Settings, Authentication]

[FILES]
This script uses an INFO file (metadata) and DATA file (actual logs).

[RETRIEVAL]
To limit the amount of time taken fetching the actual audit logs, this is limited to 24h per default.
Longer times are possible up to a max of three months.
```
### Run

```
python AuditLogs.py

```
