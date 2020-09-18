import os
import json
import threading
import time
from django.http import JsonResponse

global_object = {}
global_lock = threading.Lock()

def cleanup_thread():

    while True:
        for client in list(global_object):
            for tab_id in list(global_object[client]['tab_list']):
                try:
                    if global_object[client]['tab_list'][tab_id]['to_be_removed'] == True:
                        close_tab_handler(global_object[client],tab_id)
                except Exception as exc:
                    None
        time.sleep(60)

t = threading.Thread(target=cleanup_thread)
t.setDaemon(True)
t.start()

def user_authenticated(function):
    def wrap(request, *args, **kwargs):
        #User not authenticated
        if request.user.is_authenticated:
            return function(request, *args, **kwargs)
        else:
            v_return = {}
            v_return['v_data'] = ''
            v_return['v_error'] = True
            v_return['v_error_id'] = 1
            return JsonResponse(v_return)
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap

def database_timeout(function):
    def wrap(request, *args, **kwargs):

        v_return = {
            'v_data': '',
            'v_error': False,
            'v_error_id': -1
        }

        v_session = request.session.get('omnidb_session')

        json_object = json.loads(request.POST.get('data', None))
        v_database_index = json_object['p_database_index']

        #Check database prompt timeout
        v_timeout = v_session.DatabaseReachPasswordTimeout(int(v_database_index))
        if v_timeout['timeout']:
            v_return['v_data'] = {'password_timeout': True, 'message': v_timeout['message'] }
            v_return['v_error'] = True
            return JsonResponse(v_return)
        else:
            return function(request, *args, **kwargs)
    wrap.__doc__ = function.__doc__
    wrap.__name__ = function.__name__
    return wrap

def close_tab_handler(p_client_object,p_tab_object_id):
    try:
        tab_object = p_client_object['tab_list'][p_tab_object_id]
        del p_client_object['tab_list'][p_tab_object_id]
        if tab_object['type'] == 'query' or tab_object['type'] == 'connection':
            try:
                tab_object['omnidatabase'].v_connection.Cancel(False)
            except Exception:
                None
            try:
                tab_object['omnidatabase'].v_connection.Close()
            except Exception as exc:
                None
        elif tab_object['type'] == 'debug':
            tab_object['cancelled'] = True
            try:
                tab_object['omnidatabase_control'].v_connection.Cancel(False)
            except Exception:
                None
            try:
                tab_object['omnidatabase_control'].v_connection.Terminate(tab_object['debug_pid'])
            except Exception:
                None
            try:
                tab_object['omnidatabase_control'].v_connection.Close()
            except Exception:
                None
            try:
                tab_object['omnidatabase_debug'].v_connection.Close()
            except Exception:
                None
        elif tab_object['type'] == 'terminal':
            if tab_object['thread']!=None:
                tab_object['thread'].stop()
            if tab_object['terminal_type'] == 'local':
                tab_object['terminal_object'].terminate()
            else:
                tab_object['terminal_object'].close()
                tab_object['terminal_ssh_client'].close()

    except Exception as exc:
        None

def clear_client_object(
    p_client_id = None
):
    try:
        client_object = global_object[p_client_id]

        for tab_id in list(client_object['tab_list']):
            global_object[p_client_id]['tab_list'][tab_id]['to_be_removed'] = True
        try:
            client_object['polling_lock'].release()
        except:
            None
        try:
            client_object['returning_data_lock'].release()
        except:
            None
        #del global_object[p_client_id]
    except Exception as exc:
        print(str(exc))
        None

def get_client_object(p_client_id):
    #get client attribute in global object or create if it doesn't exist
    try:
        client_object = global_object[p_client_id]
    except Exception as exc:
        client_object = {
            'id': p_client_id,
            'polling_lock': threading.Lock(),
            'returning_data_lock': threading.Lock(),
            'returning_data': [],
            'tab_list': {}
        }
        global_object[p_client_id] = client_object

    return client_object

def get_database_object(
    p_session = None,
    p_tab_id = None,
    p_attempt_to_open_connection = False
):

    v_session = p_session.get('omnidb_session')
    v_client_id = p_session.session_key

    v_client_object = get_client_object(v_client_id)
    v_tab_global_database_object = v_session.v_tab_connections[p_tab_id]

    # Retrieving tab object
    try:
        tab_object = v_client_object['tab_list'][p_tab_id]
    except Exception as exc:
        # Create global lock object
        v_tab_global_database_object.v_lock = threading.Lock()
        tab_object =  {
            'omnidatabase': v_tab_global_database_object,
            'type': 'connection',
            'to_be_removed': False
        }
        v_client_object['tab_list'][p_tab_id] = tab_object

    if tab_object['to_be_removed']:
        raise('Database object marked to be destroyed.')

    #tab_object['database_object_lock'].acquire()

    # Try to open connection if not opened yet
    if p_attempt_to_open_connection and not tab_object['omnidatabase'].v_connection.v_con or tab_object['omnidatabase'].v_connection.GetConStatus() == 0:
        tab_object['omnidatabase'].v_connection.Open()

    return tab_object['omnidatabase']

def release_database_object(
    p_client_id = None,
    p_tab_id = None
):
    v_client_object = get_client_object(p_client_id)

    # Retrieving tab object
    try:
        tab_object = v_client_object['tab_list'][p_tab_id]
        tab_object['database_object_lock'].release()
    except Exception as exc:
        None
