import os
from configparser import configParser

dirname = os.path.dirname(__file__)
workdir = os.path.realpath(dirname)
configfile = os.sep.join([workdir, "proxy.conf"])

class ProxyConfig(object):
    def __init__(self, proxyconf):
        conf = configParser()
        if conf.read(proxyconf):
            self.logfile = conf.get('conf', 'logfile', '')
            self.db = conf.get('conf', 'db', '')
            self.table = conf.get('conf', 'table', '')
            self.path = conf.get('conf', 'path', '')
            self.datavolume = conf.get('conf', 'datavolume', '')
            self.confvolume = conf.get('conf', 'confvolume', '')
            self.exportfile = conf.get('conf', 'exportfile', '')
            self.vip = conf.get('conf', 'vip', '')


config = ProxyConfig(configfile)
