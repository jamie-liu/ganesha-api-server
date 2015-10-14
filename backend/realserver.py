from flask import Flask
import subprocess
import logging

app = Flask(__name__)


# Start real server
def start():
    logfile = '/var/log/nfs-server.log'
    logformat = '[%(asctime)s] [%(levelname)s] [LINE %(lineno)d] %(message)s'
    logging.basicConfig(filename=logfile, filemode='a',format=logformat,datefmt='%Y-%m-%d %H:%M:%S %p',level=logging.INFO)
    logging.info('NFS real server started...')


# Add the export with export_id dynamically
@app.route('/ganesha/add/<export_id>', methods=['POST'])
def addExport(export_id):
    # Issue dbus send command
    cmd = "dbus-send --print-reply --system --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr org.ganesha.nfsd.exportmgr.AddExport string:/etc/ganesha/export.conf string:''EXPORT(Export_Id={0})".format(export_id)
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    if process.returncode:
        logging.error(err)
        if "org.freedesktop.DBus.Error.InvalidFileContent" in err:
            return 'Export {0} already exists'.format(export_id), 200
        return "Failed to add export, ganesha server internal error", 503

    return '', 201


# Remove the export with export_id dynamically
@app.route('/ganesha/add/<export_id>', methods=['DELETE'])
def removeExport(export_id):
    # Issue dbus send command
    cmd = "dbus-send --print-reply --system --dest=org.ganesha.nfsd /org/ganesha/nfsd/ExportMgr org.ganesha.nfsd.exportmgr.RemoveExport uint16:{0})".format(export_id)
    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode:
        logging.error(err)
        if "org.freedesktop.DBus.Error.InvalidArgs" in err:
            return 'Export {0} does not exist'.format(export_id), 404

        return "Failed to add export, ganesha server internal error", 503

    return '', 200


if __name__ == "__main__":
    start()
    app.run(host='0.0.0.0', port=8080)
