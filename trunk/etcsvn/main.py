import os, sys
from os.path import join
from urlparse import urlparse
from ConfigParser import ConfigParser
import pysvn

from etcsvn.util import md5sum, unroot
from etcsvn.util import get_file_info

class ExistsError(IOError):
    pass

class NoFileError(IOError):
    pass


class EtcSvnConfig(ConfigParser):
    def get_files(self, section):
        data = self.get(section, 'files')
        return [x.strip() for x in data.split('\n') if x.strip()]
    
class EtcSvn(object):
    def __init__(self, cfg):
        self.maincfg = cfg
        self.cfg = EtcSvnConfig()
        self.workspace = self.maincfg.get('workspace', 'wcpath')
        self.svn = pysvn.Client()
        self.repos_url = self.maincfg.get('repos', 'url')
        if os.getuid() != 0:
            print 'EtcSvn must be run as root'
            sys.exit(1)
        os.umask(077)
        
    def _wspath(self, fullpath):
        return join(self.workspace, unroot(fullpath))

    def set_wspath_info(self, fullpath):
        path = self._wspath(fullpath)
        info = get_file_info(fullpath)
        for k, v in info.items():
            self.svn.propset('etcsvn:%s' % k, str(v), path)

    def get_wspath_info(self, fullpath):
        path = self._wspath(fullpath)
        atts = ['user', 'group', 'mode', 'mtime']
        info = {}
        for att in atts:
            prop = self.svn.propget('etcsvn:%s' % att, path)
            info[att] = prop[self._wspath(fullpath)]
        return info
    
    def create_repos(self):
        os.umask(077)
        parsed = urlparse(self.repos_url)
        if parsed[0] == 'file':
            path = parsed[2]
            if not os.path.isdir(path):
                os.system('svnadmin create %s' % parsed[2])
            else:
                print path, 'exists'

    def FirstTime(self):
        self.create_repos()
        if os.path.isdir(self.workspace):
            self.remove_workspace()
        self.checkout_workspace()
        self.get_config()
        
    def remove_workspace(self):
        if os.path.isdir(self.workspace):
            # copied from python library reference
            for root, dirs, files in os.walk(self.workspace, topdown=False):
                for name in files:
                    os.remove(join(root, name))
                for name in dirs:
                    os.rmdir(join(root, name))
            os.rmdir(self.workspace)
        else:
            print 'No workspace is present'
            
    def checkout_workspace(self):
        os.umask(077)
        self.svn.checkout(self.repos_url, self.workspace)

    def update_workspace(self):
        os.umask(077)
        self.svn.update(self.workspace)

    def check_file(self, fullpath):
        m = md5sum(file(fullpath))
        w = self.svn.info(self._wspath(fullpath)).checksum
        if m != w:
            self.add_file(fullpath, importfile=False)

            
    def check_files(self):
        for section in self.cfg.sections():
            for afile in self.cfg.get_files(section):
                self.check_file(afile)
                
        
    def add_file(self, fullpath, importfile=True):
        path = unroot(fullpath)
        if not os.path.isfile(fullpath):
            raise NoFileError, 'no such file %s' % fullpath
        ws = self.workspace
        dirs = os.path.dirname(path).split('/')
        cpath = ws
        rpath = '/'
        for d in dirs:
            rpath = join(rpath, d)
            cpath = join(cpath, d)
            if not os.path.isdir(cpath):
                os.mkdir(cpath)
                self.svn.add(cpath)
            self.set_wspath_info(rpath)
        base = os.path.basename(path)
        fname = join(cpath, base)
        if importfile:
            if os.path.isfile(fname):
                raise ExistsError
        data = file(fullpath).read()
        wfile = file(fname, 'w')
        wfile.write(data)
        wfile.close()
        if importfile:
            self.svn.add(fname)
        self.set_wspath_info(fullpath)
        
    def add_path(self, fullpath):
        if not os.path.exists(fullpath):
            raise NoFileError

        
    def update_from_system(self):
        for section in self.cfg.sections():
            files = self.cfg.get_files(section)
            for afile in files:
                self.add_file(afile, importfile=False)

    def export_to_system(self):
        for afile in self.cfg.get_files('main'):
            self.export_file(afile)
           
    def import_file(self, fullpath, section='main'):
        files = self.cfg.get_files(section)
        if fullpath in files:
            raise ValueError, '%s already imported' % fullpath
        if os.path.islink(fullpath):
            print fullpath, 'could not be imported'
            print 'symbolic links are not supported yet.'
            sys.exit(1)
        self.add_file(fullpath)
        files.append(fullpath)
        data = '\n'.join(files) + '\n'
        self.cfg.set(section, 'files', data)
        self.cfg.write(file(join(self.workspace, 'etcsvn.conf'), 'w'))

    def export_file(self, fullpath, section='main'):
        path = self._wspath(fullpath)
        if not os.path.isfile(path):
            raise NoFileError, 'This file %s not in the repository' % fullpath
        data = file(path).read()
        path = unroot(fullpath)
        dirs = os.path.dirname(path).split('/')
        rpath = '/'
        for d in dirs:
            rpath = join(rpath, d)
            if not os.path.isdir(rpath):
                os.mkdir(rpath)
            self.set_path_info(rpath, self.get_wspath_info(rpath))    
        newfile = file(fullpath, 'w')
        newfile.write(data)
        newfile.close()
        info = self.get_wspath_info(fullpath)
        self.set_path_info(fullpath, info)

    def set_path_info(self, fullpath, info):
        own = '%s:%s' % (info['user'], info['group'])
        os.system('chown %s %s' % (own, fullpath))
        mode = info['mode']
        # eval is dangerous
        # try to make sure its small number
        if len(mode) <= 7 and mode.isdigit():
            mode = eval(mode)
        else:
            raise RuntimeError, 'There was a bad mode value passed'
        os.chmod(fullpath, mode)
        mtime = int(info['mtime'])
        os.utime(fullpath, (mtime, mtime))
        
        

    def get_config(self):
        cpath = os.path.join(self.workspace, 'etcsvn.conf')
        if not os.path.isfile(cpath):
            print "etcsvn.conf doesn't exist"
            print 'creating blank etcsvn.conf'
            cfile = file(cpath, 'w')
            cfile.write('# EtcSvn generated blank configuration\n')
            cfile.write('[main]\n')
            cfile.write('files:\n\n')
            cfile.close()
            self.svn.add(cpath)
        self.cfg.read(cpath)
        

    def commit(self, msg='Automatic Commit'):
        self.svn.checkin(self.workspace, msg)
        
    def show_status(self):
        os.system('svn status %s' % self.workspace)
        
    def get_filelist(self):
        return self.cfg.get_files('main')

    def diff(self, recurse=True):
        return
