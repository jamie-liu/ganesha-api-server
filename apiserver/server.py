import subprocess
import os, errno, stat
import pycurl
import logging
import datetime
from flask import Flask
from flask import request
from sqlalchemy import func,exc
from db import init_db, db_session, Export
from config import config

app = Flask(__name__)

# Start api server
def start():
    logformat = '[%(asctime)s] [%(levelname)s] [LINE %(lineno)d] %(message)s'
    logging.basicConfig(filename=config.logfile, filemode='a',format=logformat,datefmt='%Y-%m-%d %H:%M:%S %p',level=logging.WARNING)

    try:
        init_db()
    except exc.SQLALchemyError as e:
        logging.error(e)
        raise
    logging.info('NFS api server started...')

# Get active real server list
def get_active_realserver():
    realserver = []
    # Run ipvsadm command and get active connections
    process = subprocess.Popen("ipvsadm -ln | awk '/Route / {print $2}' | awk -F: '{print $1}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()

    if process.returncode == 0:
        out = out.strip('\n')
        realserver = out.split('\n')

    return realserver

# Add export to nfs-ganesha config file
def add_export_entry(config_file, export_id, user_name, volume_name, iptable, access_type):
    # Generate the export entry
    export_block = "#<EXPORT {0}>#\n".format(export_id)
    export_block += "EXPORT{\n"
    export_block += "Export_Id={0};\n".format(export_id)
    export_block += "Path='/{0};\n".format(user_name)
    export_block += "Pseudo=/{0};\n".format(user_name)
    export_block += "FSAL{\n"
    export_block += "name='GLUSTER';\n"
    export_block += "hostname='127.0.0.1';\n"
    export_block += "volume='{0}';\n".format(volume_name)
    export_block += "volpath='/{0}';\n".format(user_name)
    export_block += "}\n"
    export_block += "Disable_ACL=TRUE;\n"
    export_block += "PrefRead=1048576;\n"
    export_block += "PrefWrite=1048576;\n"
    export_block += "CLIENT{\n"
    export_block += "Clients='{0}';\n".format(iptable)
    export_block += "Access_Type={0};\n".format(access_type)
    export_block += "}\n"
    export_block += "}\n"
    export_block += "#<EXPORT {0}>#\n".format(export_id)

    # Write to config file
    try:
        file = open(config_file, "a+")
        if file:
            file.write(export_block)
            file.flush()
            file.close()
    except IOError as e:
        logging.error(e)
        return False

    return True


# Remove export from config file
def remove_export_entry(config_file, export_id):
    cmd = "/#<EXPORT {0}>#/,/#<EXPORT {0}>#/".format(export_id)
    try:
        subprocess.call(["sed", "-i", cmd, config_file])
    except OSError as e:
        logging.error(e)
        return False

    return True


# Add export to nfs-ganesha server
def add_export(config_file, export_id, user_name, volume_name, iptable, access_type):
    if not add_export_entry(config_file, export_id, user_name, volume_name, iptable, access_type):
        return False

    realserver = get_active_realserver()
    if len(realserver) > 0:
        try:
            c = pycurl.Curl()
            for ip in realserver:
                url = 'http://{0}:8080/ganesha/add/{1}'.format(ip, export_id)
                c.setopt(c.URL, url)
                c.perform()
                retcode = c.getinfo(c.HTTP_CODE)
                if retcode != 201:
                    if retcode == 500:
                        err = "IP({0}) failed to add export {1}".format(ip, export_id)
                    else:
                        err = "IP({0}) return http code({1}) when adding export {2}".format(ip, retcode, export_id)

                    logging.error(err)
                    return False
        except pycurl.error as e:
            logging.error(e)
            return False
    else:
        err = "No active real server available"
        logging.error(err)
        return False

    return True


# Remove export from nfs-ganesha server
def remove_export(config_file, export_id):
    realserver = get_active_realserver()
    if len(realserver) > 0:
        try:
            c = pycurl.Curl()
            for ip in realserver:
                url = 'http://{0}:8080/ganesha/remove/{1}'.format(ip, export_id)
                c.setopt(c.URL, url)
                c.perform()
                retcode = c.getinfo(c.HTTP_CODE)
                if retcode != 201:
                    if retcode == 500:
                        err = "IP({0}) failed to remove export {1}".format(ip, export_id)
                    else:
                        err = "IP({0}) return http code({1}) when removing export {2}".format(ip, retcode, export_id)

                    logging.error(err)
                    return False
        except pycurl.error as e:
            logging.error(e)
            return False
    else:
        err = "No active real server available"
        logging.error(err)
        return False

    return remove_export_entry(config_file, export_id)


# Flask remove database sessions automatically when app shutdown
@app.teardown_appcontext
def shutdown_session():
    db_session.remove()

# Acquire token
@app.route('/api/public/v1/shares', methods=['POST'])
def create_share():
    dic = request.json.get('share')
    if not dic:
        return 'Incorrect HTTP parameter', 400

    name = dic.get('name')
    size = dic.get('size')

    if not (name and size and size.isdigit()):
        return 'Incorrect HTTP parameter', 400

    export_location = '{0}:/{1}'.format(config.vip, name)
    # Check if the share exist or not
    result = Export.query.filter_by(user_name = name).first()

    if result:
        share = {
            'name': name,
            'export_location': export_location,
            'size': result.quota + 'GB'
        }
        return share, 300
    else:
        # Query the maximum export id and get the next volume to be used
        res = db_session.query(func.max(Export.export_id)).first()
        volume_list = config.datavolume.split(',')
        if res[0]:
            volume_name = volume_list[result[0]%len(volume_list)]
        else:
            volume_name = volume_list[0]

        # Create new share directory if share not exist
        dir = '{0}{1}/{2}'.format(config.path, volume_name, name)
        try:
            os.mkdir(dir)
            os.chmod(dir, stat.S_IRWXU+stat.S_IRWXG+stat.S_IRWXO)
        except OSError as e:
            if e.errno != errno.EEXIST:
                logging.error(e)
                return 'Internal server error', 500

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # Set the share status to 1(online)
            export = Export(name, 1, size, export_location, volume_name, now)
            db_session.add(export)
            db_session.commit()
        except exc.SQLALchemyError as e:
            db_session.rollback()
            logging.error(e)
            return 'Internal server error', 500

        share = {
            'name': name,
            'export_location': export_location,
            'size': size + 'GB'
        }

        return share, 201


@app.route('/api/public/v1/shares/<username>', methods=['DELETE'])
def delete_share(username):
    # Check if the share exist or not
    result = Export.query.filter_by(user_name=username).first()
    if result:
        # Check if the share is online ot not
        if result.status:
            # Remove the export if the iptable has valid ip
            if result.iptable:
                if not remove_export(config.exportfile, result.export_id):
                    return 'Failed to remove export', 500

            try:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                result.status = 0
                result.iptable = None
                result.update_time = now
                db_session.commit()
            except exc.SQLALchemyError as e:
                db_session.rollback()
                logging.error(e)
                return 'Internal server error', 500

        return 'share removed', 200
    else:
        return 'share not found', 404


# Query user share information
@app.route('/api/public/v1/shares/<username>', methods=['GET'])
def query_share(username):
    # Check if the share exist or not
    result = Export.query.filter_by(user_name=username).first()
    if result:
        if result.iptable:
            iptable = result.iptable.split(',')
        else:
            iptable = []

        status = ['offline', 'online']
        share = {
            'name': username,
            'export_location': result.location,
            'size': result.quota + 'GB',
            'status': status[result.status],
            'metadata': {'iptable': iptable}
        }
        return share, 200
    else:
        return 'share not found', 404


@app.route('/api/public/v1/shares/<username>', methods=['POST'])
def update_share(username):
    dic = request.json.get('share')
    if not dic:
        return 'Incorrect HTTP parameter', 400

    size = dic.get('size')

    if not (size and size.isdigit()):
        return 'Incorrect HTTP parameter', 400

    # Check if the share exist or not
    result = Export.query.filter_by(user_name=username).first()
    if result:
        if not result.status:
            return 'share is offline', 400

        if size != result.quota:
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Update the share
            try:
                result.quota = size
                result.update_time = now
                db_session.commit()
            except exc.SQLALchemyError as e:
                db_session.rollback()
                logging.error(e)
                return 'Internal server error', 500

            if result.iptable:
                iptable = result.iptable.split(',')
            else:
                iptable = []

            status = ['offline', 'online']
            share = {
                'name': username,
                'export_location': result.location,
                'size': size + 'GB',
                'status': status[result.status],
                'metadata': {'iptable': iptable}
            }
            return share, 200
        else:
            return 'share not found', 404


@app.route('/api/public/v1/shares/<username>/metadata', methods=['POST'])
def set_share_metadata(username):
    pass


# List all user share details
def query():
    shares = []
    status = ['offline', 'online']
    results = Export.query.all()
    if results:
        for row in results:
            if row.iptable:
                iptable = row.iptable.split(',')
            else:
                iptable = []

            share = {
                'name': row.user_name,
                'export_location': row.location,
                'size': row.quota + 'GB',
                'status': status[row.status],
                'metadata': {'iptable': iptable}
            }
            shares.append(share)

    return shares, 200

if __name__ == '__main__':
    start()
    app.run(host='0.0.0.0', port=8080)
