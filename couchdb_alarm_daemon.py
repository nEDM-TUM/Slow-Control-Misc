#!/usr/bin/env python
import imp
import re
import cloudant
import threading
import time
import signal
import sys
import os
import select
import smtplib
import json
from email.mime.text import MIMEText

class logging(object):
    @classmethod
    def return_msg(cls, msg, level):
        sys.stdout.write("""["log", "%s", {"level" : "%s"}]\n""" % (msg, level))
        sys.stdout.flush()
    @classmethod
    def error(cls, msg):
        cls.return_msg(msg, "error")
    @classmethod
    def info(cls, msg):
        cls.return_msg(msg, "info")
    @classmethod
    def debug(cls, msg):
        cls.return_msg(msg, "debug")
        

_acct = cloudant.Account(uri="http://127.0.0.1:5984") 
_email_agent = None 
_all_emails = []

_alarm_dict = {}
_alarm_lock = threading.Lock()
_should_stop = False

# Define special exceptions
"""
   These exceptions can be raised by alarm modules when a notification should be
   sent.  For example:

     def main(db): 
         if alarm_condition == True:
             AlarmError("error seen here", "More descriptive text about the error")


   It is important to not that there are normal alarms, like:

     AlarmWarning, AlarmError, and AlarmCritical

   which are sent to indicate some level of error or warning.  Subsequent
   raising of such alarms (before a clear or change of alarm type), which cause 
   the alarm to be squelched.  In contrast:

     AlarmEvent

   is a generic event and will always be sent to the user, regardless if
   another event happened.  It is also automatically sent if an alarm clears. 

"""
class CouchDBAlarmException(Exception):
    def __init__(self, short_msg, long_msg=""):
        self.short_msg = short_msg
        self.long_msg = long_msg

class AlarmEvent(CouchDBAlarmException):
    """
      This is a special exception that may be raised in 'main' functions to
      forcefully remove an alarm. Otherwise, an alarm will be removed as soon
      as the function no longer throws an exception. 
    """
    pass

class AlarmWarning(CouchDBAlarmException):
    pass

class AlarmError(CouchDBAlarmException):
    pass
        
class AlarmCritical(CouchDBAlarmException):
    pass

"""
  End exceptions
"""

# Define helper functions

def alarm_send_arguments(*args):
    """
      Send JSON to stdout 
    """
    sys.stdout.write(json.dumps(list(args)) + '\n')
    sys.stdout.flush()

def alarm_get_config(*args): 
    """
      Get a configuration parameter from couchdb
    """
    alarm_send_arguments("get", *args) 
    return json.loads(sys.stdin.readline())

def alarm_latest_value(db, var_name, group_level=100):
    """
    Get the latest value of a given variable, this returns the output from the
    _stat function, which will look like:

      { u'rows': [
                   {u'value': {u'count': 1, 
                               u'max': 8.35961456298828, 
                               u'sum': 8.35961456298828, 
                               u'sumsqr': 69.88315564172574, 
                               u'min': 8.35961456298828}, 
                    u'key': [u'Bx', 2014, 4, 4, 13, 7, 22]}
                 ]
      }

    If a group_level is given <=6, then the values will be agregated.  (This is an
    efficient way to look e.g. for extremes over the last minute/hour/day/etc.)  
    """
    return db.design('slow_control_time').view('slow_control_time').get( 
        params=dict(descending=True,
                    endkey=[var_name],
                    startkey=[var_name, {}],
                    group_level=group_level,
                    limit=1,
                    )).json()

def alarm_get_recent_alarm(doc):
    """
	  Look for the most recent alarm.  This is mostly called if the daemon is
      restarted.
    """
    anid = doc['_id'] 
    db = _acct[doc['db']]
    res = db.design('alarm').view('alarm').get( 
        params=dict(descending=True,
                    endkey=[anid],
                    startkey=[anid, {}],
                    reduce=False, 
                    limit=2,
                    )).json()
    if len(res['rows']) >= 2:
        return res['rows'][-1]['key'][-1]
    return None



def alarm_update_status(db, an_id, astat):
    db.design('nedm_default').post('_update/insert_with_timestamp/' + an_id,
      params={ 'status' : astat } )

def alarm_internal_error(db, an_id, msg):
    """
      Update the status with an internal error
    """
    alarm_update_status(db, an_id, { 'error' : msg } )

def alarm_send_email(**kwargs):
    """
      Send an email with the alarm message
    """
    global _email_agent
    if _email_agent is None: return
    emails = kwargs.get('emails', []) 
    emails.extend(_all_emails)

    msg = kwargs['alarm']
    desc = kwargs.get('description', '')
    alarm_name = kwargs.get('name', '')
    # Construct the email
    name = re.match('Alarm(.*)', msg.__class__.__name__).group(1)
    toaddrs = ",".join(set(emails))
    fromaddr = "nEDM Alarm Service <mmarino@gmail.com>"
    email_msg = MIMEText("""
Name: 
  %(name)s

Description: 
  %(desc)s

Message:
  %(msg)s

""" % {"name" : alarm_name, "desc" : desc, "msg" : msg.long_msg})
    email_msg['From'] = fromaddr 
    email_msg['To'] = toaddrs 
    email_msg['Subject'] = "[nEDM Alarm, %s] %s" % ( name, msg.short_msg )

    # Send...
    try:
        _email_agent["smtp"].sendmail(fromaddr, toaddrs, email_msg.as_string())
        if "tried" in _email_agent:
            del _email_agent["tried"]
    except smtplib.SMTPServerDisconnected as e:
        if "tried" in _email_agent: 
            logging.error("Email failure...")
            del _email_agent["tried"]
        else:
            _email_agent["smtp"] = smtplib.SMTP(_email_agent["addr"], 25)
            _email_agent["tried"] = True
            alarm_send_email(**kwargs)
    except smtplib.SMTPException as e:
        logging.error("Error sending mail: " + repr(e))

def alarm_append_alarm(doc, haslock=True, email_when_new=False):
    """
      Add an alarm to those currently being monitored
    """
    global _alarm_dict
    try:
        if 'status' in doc and 'error' in doc['status']: return 
        doc['mod'] = imp.new_module(doc['_id'])
        am = doc['mod']
        exec doc['code'] in am.__dict__

        # Export exceptions, some API to the module, etc.
        am.__dict__['latest_value'] = lambda x,y=100: alarm_latest_value(_acct[doc['db']], x, y) 
        for exc in [ AlarmWarning, AlarmError, AlarmCritical, AlarmEvent ]:
            am.__dict__[exc.__name__] = exc

        if 'emails' not in doc:
            doc['emails'] = []

        triggered = alarm_get_recent_alarm(doc)
        if triggered is not None:
            doc['triggered'] = triggered 
        elif email_when_new:
            alarm_send_email(alarm=AlarmEvent("New alarm", "Alarm was created"), **doc)

        # Add to the alarm_dictionary. This will also replace alarms that have
        # been updated and reset their "triggered" status. 
        if not haslock: _alarm_lock.acquire()
        _alarm_dict[doc['_id']] = doc
        if not haslock: _alarm_lock.release()

    except Exception as e:
        db = _acct[doc['db']]
        alarm_internal_error(db, doc['_id'], repr(e))


def alarm_monitor_changes_feed(db):
    """
      Monitor changes feed for a particular database  
    """
    logging.info("Starting changes feed for: %s" % db)
    adb = _acct[db]
    ch = adb.changes(params=dict(feed='continuous',
                                 heartbeat=5000,
                                 since='now',
                                 filter='nedm_default/doc_type',
                                 type='alarm',
                                 handle_deleted=True),
                      emit_heartbeats=True)
    for l in ch:
        if l is None and _should_stop: break
        if l is None: continue
        if "deleted" in l:
            # Delete from the alarm list
            _alarm_lock.acquire()
            if l["id"] in _alarm_dict:
                logging.info("Removing: " + l["id"])
                del _alarm_dict[l["id"]]
            _alarm_lock.release()
        else: 
            # Add to the alarm list
            logging.info("Appending: " + l["id"])
            doc = adb.get(l["id"]).json()
            doc['db'] = db
            alarm_append_alarm(doc, False, True)
    logging.info("Finishing changes feed for: %s" % db)

def alarm_save_in_database(db, a, anid):
    """
      Save a notice in the database that an alarm has been triggered
    """
    db.design('nedm_default').post('_update/insert_with_timestamp',
      params=dict(type="triggered_alarm",
                  alarm_type=a.__class__.__name__,
                  alarm_id=anid,
                  msg=dict(brief=a.short_msg,verbose=a.long_msg)))
            
def alarm_run_check(alarm_dict):
    """
      Check a particular alarm condition 
    """
    m = alarm_dict['mod']
    db = _acct[alarm_dict['db']] 
    triggered = None
    try:
        m.main(db)
        if 'triggered' in alarm_dict and \
          alarm_dict['triggered'] != 'AlarmEvent':
            raise AlarmEvent("Alarm Removed", "Alarm was removed")
    except (AlarmWarning, AlarmError, AlarmCritical, AlarmEvent) as a:
        # Handle our alarms, writing to DB and sending emails if necessary 
        triggered = a.__class__.__name__
        # We always send an email on AlarmEvent
        if "triggered" not in alarm_dict or \
          triggered == "AlarmEvent" or      \
          alarm_dict["triggered"] != triggered:
            alarm_send_email(alarm=a,**alarm_dict)
            alarm_save_in_database(db, a, alarm_dict['_id'])
    except Exception as e:
        # Something else happened, but we didn't expect it.  Don't call this
        # alarm again
        alarm_internal_error(db, alarm_dict['_id'], repr(e))
    return triggered
        
def alarm_signal_handler(*args):
    """
      Handle signals/requests to exit 
    """
    global _should_stop
    if not _should_stop: logging.info("Stop Requested")
    _should_stop = True

def alarm_watch_for_input():
    """
      Watches for input, and once an EOF is seen request a program end. 
    """
    # We do a loop to see if there's been a request to stop.
    while not _should_stop:
       i, _, __ = select.select( [sys.stdin], [], [], 1 )
       if not i: continue
       x = sys.stdin.read(1)
       if x == "":
           alarm_signal_handler()
           break

def alarm_main():
    """
      Main process for running the alarm daemon
    """
    global _email_agent, _all_emails

    logging.info("Beginning alarm daemon")
    # Grab the configuration information
    all_daemons = alarm_get_config("os_daemons")
    my_name = None
    my_file = os.path.basename(__file__)
    for k, v in all_daemons.items():
        if re.search(my_file, v):
            my_name = k
            logging.info("Found name, running as: " + my_name)
            break
        
    if my_name:
        logging.info("Registering for restart")
        alarm_send_arguments("register", my_name)

        my_config = alarm_get_config(my_name)
        if 'username' in my_config and \
           'password' in my_config:
            if not (_acct.login(my_config['username'], 
                                my_config['password']).status_code == 200):
                logging.error("UN/Password incorrect")
                sys.exit(1)
            logging.info("Using UN/PW from config")

        if 'email_agent' in my_config:
            _email_agent = dict(smtp=smtplib.SMTP(my_config['email_agent'], 25),
                                addr=my_config['email_agent'])
            logging.info("Using email agent: " + my_config['email_agent']) 
        _all_emails = json.loads(my_config.get('emails', "[]")) 
        logging.info("Using default emails: " + ','.join(_all_emails))

    # First grab all the alarms that we need to deal with
    all_dbs = [db.replace("/", "%2F") for db in _acct.all_dbs().json()
                 if re.match("nedm/.*", db)]

    for db in all_dbs:
        adb = _acct[db]
        alarm_docs = adb.design("document_type").view("document_type").get(
            params=dict(endkey=["alarm", {}],
                        startkey=["alarm"],
                        reduce=False,
                        include_docs=True
                       )).json()
        for r in alarm_docs['rows']:
            doc = r['doc']
            doc['db'] = db
            alarm_append_alarm(doc, True, False)

    # Start monitoring threads for new alarms
    threads = [threading.Thread(target=alarm_monitor_changes_feed, args=(db,)) 
                for db in all_dbs]
    # Monitor thread for program stop
    threads.append(threading.Thread(target=alarm_watch_for_input))
    for th in threads: th.start()
    # Handle interrupts as well
    signal.signal(signal.SIGINT, alarm_signal_handler)

    i = 0
    while not _should_stop: 
        i += 0.5
        if i < 20:
            time.sleep(0.5) 
            continue
        i = 0

        logging.debug("Running check...")
        # Graph a copy of the alarms so we can then release the lock
        _alarm_lock.acquire()
        alarms_copy = _alarm_dict.copy()
        _alarm_lock.release()

        triggered = {} 
        for k, v in alarms_copy.items():
            if 'status' in v and \
              'disabled' in v['status']: continue
            o = alarm_run_check(v)
            if o is not None: 
                triggered[k] = o 
        
        # Update whether or not we have triggered on an alarm, save the last
        # trigger
        _alarm_lock.acquire()
        for k, v in _alarm_dict.items():
            if "triggered" in v and k not in triggered:
                del v["triggered"]
            if k in triggered:
                v["triggered"] = triggered[k] 
        _alarm_lock.release()

    logging.debug("Joining threads")
    for th in threads: th.join()

if __name__ == '__main__':
    try: 
        alarm_main()
    except Exception as e:
        logging.error("Error seen: " + repr(e))
