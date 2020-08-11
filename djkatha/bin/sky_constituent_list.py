"""SKY API Authentication/Query Scripts
Modified from code by Mitch Hollberg
(mhollberg@gmail.com, mhollberg@cfgreateratlanta.org)
Python functions to
    a) Get an initial SKYApi token/refresh token and write them to a local file
    b) Make subsequent refreshes and updates to the SKYApi authentication
    based on tokens in the files.
"""
 
# import requests
import sys
import os
import argparse
import pyodbc
import datetime
from datetime import datetime, date, timedelta
from time import strftime, strptime
import django


# Note to self, keep this here
# django settings for shell environment
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djkatha.settings.shell")
django.setup()
# ________________

# django settings for script
from django.conf import settings
from django.core.cache import cache

from djkatha.core.sky_api_auth import fn_do_token
from djkatha.core.sky_api_calls import get_constituents_custom_field_list, \
    get_lookup_id
from djimix.core.utils import get_connection, xsql

# informix environment
os.environ['INFORMIXSERVER'] = settings.INFORMIXSERVER
os.environ['DBSERVERNAME'] = settings.DBSERVERNAME
os.environ['INFORMIXDIR'] = settings.INFORMIXDIR
os.environ['ODBCINI'] = settings.ODBCINI
os.environ['ONCONFIG'] = settings.ONCONFIG
os.environ['INFORMIXSQLHOSTS'] = settings.INFORMIXSQLHOSTS

# normally set as 'debug" in SETTINGS
DEBUG = settings.INFORMIX_DEBUG
desc = """
    Collect data from Blackbaud
"""
parser = argparse.ArgumentParser(description=desc)

parser.add_argument(
    "--test",
    action='store_true',
    help="Dry run?",
    dest="test"
)
parser.add_argument(
    "-d", "--database",
    help="database name.",
    dest="database"
)
"""
    12/9/19 - The API call to get_constituent_list can be filtered by student
         status and add date.   
          
         So the process would involve getting a current list of those with 
         a custom_field_category=Student Status where date added > whatever date
          
         Then I can write the CX id numbers and the Blackbaud ID numbers to a
         file or table, read them back, and use the blackbaud ID to pass any 
         changes to Blackbaud
    
         The process would have to involve finding the status of active students
         in CX, (Look for a change date...to limit the number.  Maybe audit table)
        
         Then determine if the student is in Raiser's Edge by reading the list
         just retrieved. 
    
         Currently the student adds would be periodic O-Matic processes, 
         but I would possibly need to create the custom field record if 
         O-Matic doesn't create it 
           
         May be easiest to just purge the table and repopulate it periodically
         What about graduations then?
            
      If not add student  ??,
          then add the custom field record  ???
      Else - find out of custom field record exists
          If not add
          else update

      So each student will require 1-2 API calls
    
      No way to test any of this because there are no students in RE yet...
"""


def fn_update_local(carth_id, bb_id):
    try:

        q_upd_sql = '''UPDATE cvid_rec
                SET re_api_id = ? WHERE cx_id = ?
                '''
        q_upd_args = (bb_id, carth_id)
        connection = get_connection(EARL)
        # print(q_upd_sql)
        print(carth_id)
        with connection:
            cur = connection.cursor()
            cur.execute(q_upd_sql, q_upd_args)
            return 1
    except pyodbc.Error as err:
            # print("Error in fn_update_local:  " + str(err))
            sqlstate = err.args[0]
            # print(sqlstate)
            return 0


def main():
    try:
        # set global variable
        global EARL

        # determines which database is being called from the command line
        if database == 'cars':
            EARL = settings.INFORMIX_ODBC
        if database == 'train':
            EARL = settings.INFORMIX_ODBC_TRAIN
        # if database == 'sandbox':
        #     EARL = settings.INFORMIX_ODBC_SANDBOX

        """"--------GET THE TOKEN------------------"""
        current_token = fn_do_token()
        # print("Current Token = ")
        # print(current_token)

        # print(EARL)
        """-----Get a list of constituents with a custom field of 
            Student Status - STORE the id in cvid_rec-------"""
        """---We need this to match Carthage ID to Blackbaud ID------"""

        """
           UPDATE 1/17/20  It will more likely be the case that we will get
           a csv list from advancement of the students added.  If so, we 
           can read that csv and find the BB_ID only for those students"""

        # searchtime = date.today() + timedelta(days=-60)
        # print("Searchtime = " + str(searchtime))

        """The date of the last search will be stored in Cache"""
        searchtime = cache.get('last_const_date')
        # print("last_const_date = " + str(searchtime))

        # API call to get BB ID
        x = get_constituents_custom_field_list(current_token, str(searchtime))
        # print(x['value'])
        if x == 0:
            print("No recent student entries in RE")
        else:
            # print(x['value'])
            for i in x['value']:
                bb_id = i["parent_id"]
                print(bb_id)
                # Look for ID in cvid_rec
                chk_sql = '''select cx_id, re_api_id from cvid_rec
                    where re_api_id = {}'''.format(i['parent_id'])

                # print(chk_sql)
                connection = get_connection(EARL)

                with connection:
                    data_result = xsql(chk_sql, connection, key='debug')
                    x = data_result.fetchone()

                    # Create the cvid_rec if it doesn't exist - Will require
                    # second call to API to retrieve the carthage id using
                    # the blackbaud id

                    if x is None:
                        # print("Need to find CarthID for bb_id "
                        #       + str(bb_id))
                        carth_id = get_lookup_id(current_token, bb_id)
                        ret = fn_update_local(carth_id, bb_id)
                        print(ret)

                    else:
                        print("CVID Rec exists for" + str(x[0]))
                        # carth_id = x[0]
                        pass


            """This will set a date for use in finding the constituent list"""
            """To retrieve the date of last run"""
            searchtime = date.today()
            searchtime = searchtime.strftime('%Y-%m-%d')
            """Set the constituent last date"""
            cache.set('last_const_date', searchtime)

            # t = cache.get('last_const_date')
            # print("last_const_date = " + str(t))


    except Exception as e:
        print("Error in main:  " + str(e))
        # print(type(e))
        # print(e.args)
        sqlstate = e.args[1]
        print(sqlstate)


if __name__ == "__main__":
    args = parser.parse_args()
    test = args.test
    database = args.database

    if not database:
        print("mandatory option missing: database name\n")
        parser.print_help()
        exit(-1)
    else:
        database = database.lower()

    if database != 'cars' and database != 'train' and database != 'sandbox':
        print("database must be: 'cars' or 'train' or 'sandbox'\n")
        parser.print_help()
        exit(-1)

    if not test:
        test = 'prod'
    else:
        test = "test"

    sys.exit(main())
