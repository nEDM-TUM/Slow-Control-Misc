#!/usr/bin/env python
"""
Handles button press that is routed to the COM2 port.

Allows auto shutdown of computer since it doesn't support ACPI poweroff.  

"""
import sys
import os
from serial import Serial 
from fcntl import  ioctl
import datetime
import time
import subprocess
from termios import (
    TIOCMIWAIT,
    TIOCM_RNG,
    TIOCM_DSR,
    TIOCM_CD,
    TIOCM_CTS
)

def log(*args):
    a = list(args)
    alog = [str(datetime.datetime.utcnow()), " ".join(map(str,a))]
    sys.stdout.write(' [SERIAL] '.join(alog)+'\n')
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


class SerialDaemon(Daemon):
    def run(self):

        ser = Serial('/dev/ttyS1')
        ser.setDTR(True)
        
        wait_signals = (TIOCM_RNG |
                        TIOCM_DSR |
                        TIOCM_CD  |
                        TIOCM_CTS)
        log( "Waiting for signal...")
	last_time = None
        while True:
            try:
                ioctl(ser.fd, TIOCMIWAIT, wait_signals)
		if ser.getCD():
                    # Take action
		    now = time.time()
		    if not last_time or now - last_time > 1: 
                        last_time = now
			continue
                    else:
                        log( "CD seen within 1s")
			subprocess.call(["shutdown", "-h", "now", "Front button pressed"])
			last_time = None
            except (KeyboardInterrupt, Exception) as e:
                log("Stop requested" )
                log(e)
		break
        
        ser.setDTR(False)

def run_daemon(cmd, apath):
    join = os.path.join
    daemon = SerialDaemon(join(apath, 'ser_daemon.pid'),
                          stdout=join(apath, 'ser_daemon.log'),
                          stderr=join(apath, 'ser_daemon.err'))
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
    run_daemon(sys.argv[1], "/var/ser_daemon")
