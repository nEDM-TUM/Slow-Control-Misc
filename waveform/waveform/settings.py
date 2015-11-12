import sys

__settings_map = {
  "db_url"      : "DB_URL",
  "db_name"     : "DB_NAME",
  "db_un"       : "DB_USER_NAME",
  "db_pw"       : "DB_PASSWORD",
  "server_port" : "SERVER_PORT"
}

def _ret_value(v):
    def inner(*args):
        import os
        print v, os.environ.get(v, "")
        return os.environ.get(v, "")
    return inner

class _Settings(object):
    pass

for k, v in __settings_map.items():
    setattr(_Settings, k, property(_ret_value(v)))

sys.modules[__name__] = _Settings()
