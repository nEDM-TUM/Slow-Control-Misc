#!/usr/bin/env python
"""
Readout of UPS and Gateway machine, monitoring health variables every 30
seconds.  
"""
import sys
import os
import telnetlib
import pprint
import time
import re
import datetime
import cloudant
import requests
import subprocess

class UPSCommException(Exception):
    pass

class MonitorUPS(object):
    def __convert_function(atype):
        def __f(astr=None):
            if not astr: return atype
            return float(re.match('([0-9.]*) ' + atype, astr).group(1))
        return __f

    def __convert_time(astr=None):
        if not astr: return "min"
        ag = re.match('([0-9.]*) hr ([0-9.]*) min', astr)
        return float(ag.group(1))*60 + float(ag.group(2))

    __returned_types = {
      'Battery State Of Charge': __convert_function('%'),
      'Battery Voltage': __convert_function('VDC'),
      'Input Frequency': __convert_function('Hz'),
      'Input Voltage': __convert_function('VAC'),
      'Internal Temperature': __convert_function('C'),
      'Output Current': __convert_function('A'),
      'Output Frequency': __convert_function('Hz'),
      'Output VA Percent': __convert_function('%'),
      'Output Voltage': __convert_function('VAC'),
      'Output Watts Percent': __convert_function('%'),
      'Runtime Remaining': __convert_time,
    }
    def __init__(self, server, username, password):
        self.un = username
        self.pwd = password
        self.server = server
        self.tc = "apc>"
        self.__connect()
        
    def __connect(self):
        self.s = telnetlib.Telnet(self.server, 23) 
        self.__read_until("User Name :")
        self.__write(self.un + "\r\n")
        self.__read_until("Password  :")
        self.__write(self.pwd + "\r\n")
        self.__read_until(self.tc)

    def __read_until(self, astr):
        return self.s.read_until(astr)

    def __write(self, astr):
        self.s.write(astr)

    def cmd_and_return(self, astr):
        self.__write(astr + "\r\n")
        res = self.__read_until(self.tc).replace(astr+"\r\n", "").replace(self.tc, "").split('\r\n')
        if res[0] != "E000: Success": 
            raise UPSCommException(res[0])
        return res[1:]

    def get_health(self):
        ad = dict([o.split(': ') for o in 
                       self.cmd_and_return("detstatus -all") if o != ""])
        rt = MonitorUPS.__returned_types
        return dict([("%s %s (%s)" % (self.server, k, rt[k]()), rt[k](ad[k])) 
                       for k in ad if k in rt])

	
class GatewayMachineHealth(object):
    def __temperature(astr=None):
	if not astr: return "C" 
        return float(astr.split('/')[0])
    __check = re.compile("(.*?)  .* (\S+)\s+\Z")
    __used_keys = {
        'CPU Temperature' : __temperature, 
        'System Temperature' : __temperature 
    }
    def get_health(self):
        astr = subprocess.check_output(["sdt"])
	astr = astr.split('\n')
	check_line = "---------------"
	delim = [i for i in range(len(astr)) if astr[i][:len(check_line)] == check_line]
	adic = dict([GatewayMachineHealth.__check.match(i).groups() for i in astr[delim[0]+1:delim[1]]])
	uk = GatewayMachineHealth.__used_keys
	return dict([("GM %s (%s)" % (k, uk[k]()), uk[k](adic[k])) for k in uk]) 



def log(*args):
    a = list(args)
    alog = [str(datetime.datetime.utcnow()), " ".join(map(str,a))]
    sys.stdout.write(' [HEALTH] '.join(alog)+'\n')
    sys.stdout.flush()


"""
  From: http://www.jejik.com/articles/2007/02/a_simple_unix_linux_daemon_in_python/
  Author: Sander Marechal
"""

import sys, os, time, atexit
from signal import SIGTERM, SIGINT, SIGHUP 
import hashlib, uuid
import threading 

class Daemon:
    """
    A generic daemon class.
    
    Usage: subclass the Daemon class and override the run() method
    """
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile
    
    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced 
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit first parent
                sys.exit(0) 
        except OSError, e: 
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)
    
        # decouple from parent environment
        os.chdir("/") 
        os.setsid() 
        os.umask(0) 
    
        # do second fork
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit from second parent
                sys.exit(0) 
        except OSError, e: 
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1) 
    
        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())
    
        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile,'w+').write("%s\n" % pid)
    
    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
    
        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)
        
        # Start the daemon
        self.daemonize()
        self.run()


    def reload(self):
        pid = self.pid()
        if not pid: return
        os.kill(pid, SIGHUP)

    def pid(self):
        # Get the pid from the pidfile
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
    
        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)

        return pid # not an error in a restart


    def stop(self):
        """
        Stop the daemon
        """
        # Try killing the daemon process    
        pid = self.pid()
        if not pid: return

        try:
            while 1:
                os.kill(pid, SIGINT)
                time.sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)

    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """

class HealthDaemon(Daemon):
    def get_acct(self):
        acct = cloudant.Account("http://raid.nedm1:5984")
        requests.utils.add_dict_to_cookiejar(acct._session.cookies, 
           dict(AuthSession=""))
	return acct

    def run(self):

        gen_function = {
          "UPS" : lambda: MonitorUPS("ups.1.nedm1"),
          "GW" : lambda: GatewayMachineHealth(),
        }
	current_functions = {}
        while True:
            try:
                time.sleep(30)
		doc = { "value" : {}, "type" : "data"}
	        for k in gen_function:
                    if k not in current_functions or not current_functions[k]:
                        current_functions[k] = gen_function[k]()
	            try:
                        d = current_functions[k].get_health()
                        for x in d: doc['value'][x] = d[x]
	            except KeyboardInterrupt:
	                raise
	            except Exception as e:
			log("Error seen: ", e)
                        current_functions[k] = None
                if len(doc["value"].keys()) != 0:
                    acct = self.get_acct()
                    db = acct["nedm%2Fsystem_health"]
                    des = db.design("nedm_default")
                    des.post("_update/insert_with_timestamp", params=doc)
            except (KeyboardInterrupt) as e:
                log("Stop requested" )
		break
	    except Exception as e:
                log(e)
                pass
        
def run_daemon(cmd, apath):
    join = os.path.join
    daemon = HealthDaemon(join(apath, 'health_daemon.pid'),
                          stdout=join(apath, 'health_daemon.log'),
                          stderr=join(apath, 'health_daemon.err'))
    if 'start' == cmd:
        daemon.start()
    elif 'stop' == cmd:
        daemon.stop()
    elif 'restart' == cmd:
        daemon.restart()
    elif 'reload' == cmd:
        daemon.reload()
    else:
        print "usage: start|stop|restart|reload"

if __name__ == '__main__':
    run_daemon(sys.argv[1], "/var/health_daemon")

