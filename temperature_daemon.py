"""
  Provide a daemon to control the temperature readout.
  There are currently 2 arduinos connected.
"""
import socket
import pynedm

class SocketDisconnect(Exception):
    pass
 
class SocketObj:
    def __init__(self, address, port, term_character="\n"):
        s = socket.socket()
        s.connect((str(address), port))
        self.s = s
        self.tc = term_character
 
    def flush_buffer(self):
        astr = ""
        while 1:
            try:
                r = self.s.recv(4096)
                if not r: 
                    break
                astr += r
                if astr.find(self.tc) != -1: 
                    break
            except socket.error:
                raise SocketDisconnect("Disconnected from socket")
      
        return astr.replace(self.tc, "")
 
 
    def cmd_and_return(self, cmd, expected_return=""):
        self.s.send(cmd + "\r\n")
        return self.flush_buffer().replace(expected_return, "").rstrip().lstrip()
 

def _generate_function(ip_address, cmd, exp_ret=""):
    def _f(*args):
        s = SocketObj(ip_address, 8888, term_character="\n%")
        _cmd = cmd
        if len(args) != 0:
            _cmd += " " + str(args[0])
        astr = s.cmd_and_return(_cmd, exp_ret)
        if len(args) != 0:
            astr = s.cmd_and_return("sto")
        try:
            s.cmd_and_return("c")
        except: pass
        return astr
    return _f

def _generate_cmds_from_help(ip_address):
    h = _generate_function(ip_address, "help")
    all_lines = h().split('\n')
    cur_item = None
    ret_dic = {}
    for l in all_lines:
        x = l.split('\t')
        if len(x) < 3: continue
        if x[1].rstrip() != "": cur_item = x[1].rstrip()
        if cur_item not in ret_dic:
            ret_dic[cur_item] = []
        ret_dic[cur_item].append(x[2])
    tmp_dic = {}
    for k in ret_dic: 
        tmp_dic[k] = {}
        v = ret_dic[k]
        if len(v) == 3:
            tmp_dic[k]["format"] = v[0]
            tmp_dic[k]["units"] =  v[1]
            tmp_dic[k]["help_msg"] = v[2]
        else:
            tmp_dic[k]["help_msg"] = v[0]
            
    return tmp_dic

def _generate_cmds(ip_addrs):
    ret_dic = {}
    for ip in ip_addrs:
        d = _generate_cmds_from_help(ip)
        for k in d:
            v = d[k]
            if "format" in v:
                v["get"] = _generate_function(ip, k, k+":")
                v["set"] = _generate_function(ip, k, k+":")
            else:
                v["call"] = _generate_function(ip, k)
        ret_dic[ip] = dict(cmds=d)
    return ret_dic

def _generate_help_fn(adic):
    ret_dic = {}
    for k in ["format", "units", "help_msg"]:
        if k in adic:
            ret_dic[k] = adic[k]
    def _f():
        return ret_dic
    return _f

if __name__ == '__main__':
    # FixME, read this from the database
    d = _generate_cmds(["192.168.1.61", "192.168.1.62"])
    total_dic = {}
    for k in d: 
        for j,v in d[k]["cmds"].items():
            total_dic["%s_%s_help" % (k, j)] = _generate_help_fn(v) 
            for x in ['get', 'set', 'call']:
                if x in v:
                    key_name = "%s_%s_%s" % (k, j, x)
                    total_dic[key_name] = v[x]
                    v[x] = key_name 
        
    total_dic["all_keys"] = lambda: d

    pynedm.listen(total_dic, "nedm%2Ftemperature_environment", 
                  username="un", password="""pw""",
                  uri="http://raid.nedm1:5984")
    pynedm.wait()



