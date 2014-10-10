import cloudant
import sys
import json
import re
import logging

# global variables
_ignored_dbs = []
_handled_dbs = {}
_max_updates = 100

# Give us some logging
logging.basicConfig(filename='/path/to/update_indexer.log', level=logging.INFO)

# Authentication, this only needs to be a read-only
_acct = cloudant.Account(uri="http://127.0.0.1:5984", async=True)
_res = _acct.login("username", "password").result()
assert _res.status_code == 200

def get_views_for_db(adb):
    """
      Grab views/design documents for a given DB.
      This just grabs the initial view, since that's all we need to update all
      the views on a design doc
    """
    db = _acct[adb]
    return [(doc['id'].replace('_design/',''), doc['doc']['views'].keys()[0])
                   for doc in db.all_docs(params=dict(
                                 startkey='"_design/"',
                                 endkey='"_design0"',
                                 include_docs=True
                                 ))
                   if 'views' in doc['doc']]

def update_views(db_name, ddocs):
    """
      Update the views in a database
    """
    logging.info("Update: " +  db_name)
    adb = _acct[db_name]
    for des_doc, view in ddocs:
        adb.design(des_doc).view(view).get(
            params=dict(limit=1,stale="update_after"))

def listen(reg_exp):
    """
      Listen to stdin, and update databases that match the reg expression
      (reg_exp)
    """
    global _handled_dbs, _ignored_dbs
    while 1:
        data = sys.stdin.readline()
        if not data: break

        o = json.loads(data)
        db_name = o['db'].replace('/', '%2F')

        # Continue if we're ignoring these dbs
        if db_name in _ignored_dbs: continue

        # Check if we're handling this db
        if db_name not in _handled_dbs:
            if not re.match(reg_exp, db_name):
                logging.info("Ignoring: " + db_name)
                _ignored_dbs.append(db_name)
                continue
            _handled_dbs[db_name] = {
                                      'views' : get_views_for_db(db_name),
                                      'counter' : 0
                                    }
            logging.info("Tracking: " + db_name)

        the_db = _handled_dbs[db_name]
        # Handle types of updates, we only handle (design) doc updates
        t = o['type']
        if t == 'updated':
            # Increment counter
            the_db['counter'] += 1
        elif t == 'ddoc_updated':
            # Update views if a design document was updated
            the_db['views'] = get_views_for_db(db_name)

        # If the counter has exceeded the max_updates, update the views
        if the_db['counter'] >= _max_updates:
            update_views(db_name, the_db['views'])
            the_db['counter'] = 0

if __name__ == '__main__':
    logging.info(" ######### UPDATER starting ########## ")
    try:
        listen("nedm.*")
        logging.info(" ######### UPDATER complete ########## ")
    except Exception, e:
        # Catch all errors that cause an exit
        logging.error(repr(e))
