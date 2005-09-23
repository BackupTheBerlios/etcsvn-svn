import os, sys
from os.path import join
from urlparse import urlparse
from ConfigParser import ConfigParser
import pysvn

from etcsvn.util import md5sum, unroot
from etcsvn.util import get_file_info, copyfile
from etcsvn.util import remove_directory

class ExistsError(IOError):
    pass

class NoFileError(IOError):
    pass

def make_new_config(cfgpath):
    cfile = file(cfgpath, 'w')
    lines = ['# EtcSvn generated blank configuration',
             '[main]', 'dirs:', 'files:', '', '']
    cfile.write('\n'.join(lines))
    cfile.close()
    
class EtcSvnConfig(ConfigParser):
    def _list_lines(self, astring):
        return [x.strip() for x in astring.split('\n') if x.strip()]
        
    def get_files(self, section):
        return self._list_lines(self.get(section, 'files'))

    def get_dirs(self, section):
        return self._list_lines(self.get(section, 'dirs'))
        
    
class EtcSvn(object):
    def __init__(self, cfg):
        self.maincfg = cfg
        self.cfg = EtcSvnConfig()
        self.workspace = self.maincfg.get('workspace', 'wcpath')
        self.svn = pysvn.Client()
        self.repos_url = self.maincfg.get('repos', 'url')
        self.root_path = '/'
        self._file_atts = ['user', 'group', 'mode', 'mtime']
        if os.getuid() != 0:
            print 'EtcSvn must be run as root'
            sys.exit(1)
        os.umask(077)
        
    def _wspath(self, fullpath):
        return join(self.workspace, unroot(fullpath))

    def _rootpath(self, fullpath):
        print 'need to make provision to root files elsewhere'
    
    def _set_wspath_info(self, fullpath, wspath, info={}):
        if not info:
            info = get_file_info(fullpath)
        for k, v in info.items():
            self.svn.propset('etcsvn:%s' % k, v, wspath)
        
    def _get_wspath_info(self, wspath):
        data = {}
        for attr in self._file_atts:
            prop = self.svn.propget('etcsvn:%s' % attr, wspath)
            data[attr] = prop[wspath]
        return data
        
    def _check_wspath_info(self, fullpath, wspath):
        info = get_file_info(fullpath)
        wsinfo = self._get_wspath_info(wspath)
        return info == wsinfo, info, wsinfo

    def _check_symlink(self, fullpath, wspath):
        rtarget = os.readlink(fullpath)
        wstarget = os.readlink(wspath)
        return rtarget == wstarget, rtarget, wstarget

    def _check_file_md5(self, fullpath, wspath):
        m = md5sum(file(fullpath))
        w = self.svn.info(wspath).checksum
        return m == w
        
    
    def set_wspath_info(self, fullpath, wspath=''):
        if not wspath:
            wspath = self._wspath(fullpath)
        self._set_wspath_info(fullpath, wspath)
        
    def get_wspath_info(self, fullpath, wspath=''):
        if not wspath:
            wspath = self._wspath(fullpath)
        return self._get_wspath_info(wspath)
        
    def create_repos(self):
        os.umask(077)
        parsed = urlparse(self.repos_url)
        if parsed[0] == 'file':
            path = parsed[2]
            if not os.path.isdir(path):
                os.system('svnadmin create %s' % parsed[2])
            else:
                print path, 'exists'
        else:
            print "Can't create remote repository."
            sys.exit(1)
    
    def remove_workspace(self):
        if os.path.isdir(self.workspace):
            remove_directory(self.workspace)
        else:
            print 'No workspace is present'
            
    def checkout_workspace(self):
        os.umask(077)
        self.svn.checkout(self.repos_url, self.workspace)

    def update_workspace(self):
        os.umask(077)
        self.svn.update(self.workspace)

    def _handle_intermediate_dirs(self, fullpath, wspath=''):
        if not wspath:
            wspath = self._wspath(fullpath)
        ws = self.workspace
        path = unroot(fullpath)
        if os.path.dirname(path):
            dirs = os.path.dirname(path).split('/')
            cpath = ws
            rpath = '/'
            for d in dirs:
                rpath = join(rpath, d)
                cpath = join(cpath, d)
                if os.path.islink(rpath):
                    print 'There is a symlink in an intermediate directory'
                    sys.exit(1)
                if not os.path.isdir(cpath):
                    os.mkdir(cpath)
                    self.svn.add(cpath)
                self.set_wspath_info(rpath)
        else:
            if not os.path.isdir(wspath):
                os.mkdir(wspath)
                self.svn.add(wspath)
            self.set_wspath_info(fullpath)

    def _update_file_from_system(self, fullpath, wspath):
        if not self._check_file_md5(fullpath, wspath):
            copyfile(fullpath, wspath)
            self._set_wspath_info(fullpath, wspath)
        else:
            same, sysinfo, wsinfo = self._check_wspath_info(fullpath, wspath)
            if not same:
                self._set_wspath_info(fullpath, wspath, info=sysinfo)

    def _update_file_from_workspace(self, fullpath, wspath):
        same, sysinfo, wsinfo = self._check_wspath_info(fullpath, wspath)
        if not self._check_file_md5(fullpath, wspath):
            copyfile(wspath, fullpath)
            self.set_path_info(fullpath, info=wsinfo)
        else:
            if not same:
                self.set_path_info(fullpath, info=wsinfo)

    def _update_link_from_system(self, fullpath, wspath):
        same, rtarget, wstarget = self._check_symlink(fullpath, wspath)
        if not same:
            os.remove(wspath)
            os.symlink(rtarget, wspath)

    def _update_link_from_workspace(self, fullpath, wspath):
        same, rtarget, wstarget = self._check_symlink(fullpath, wspath)
        if not same:
            os.remove(fullpath)
            os.symlink(rtarget, fullpath)
        
    def _import_file_from_system(self, fullpath, wspath=''):
        if not wspath:
            wspath = self._wspath(fullpath)
        copyfile(fullpath, wspath)
        self.svn.add(wspath)
        self._set_wspath_info(fullpath, wspath)

    def _import_link_from_system(self, fullpath, wspath=''):
        if not wspath:
            wspath = self._wspath(fullpath)
        target = os.readlink(fullpath)
        os.symlink(target, wspath)
        self.svn.add(wspath)

    def _import_empty_dir_from_system(self, fullpath, wspath=''):
        if not wspath:
            wspath = self._wspath(fullpath)
        os.mkdir(wspath)
        self.svn.add(wspath)
        self._set_wspath_info(fullpath, wspath)

    def _update_empty_dir_from_system(self, fullpath, wspath):
        same, sysinfo, wsinfo = self._check_wspath_info(fullpath, wspath)
        if not same:
            self._set_wspath_info(fullpath, wspath, info=sysinfo)
            
    def _update_empty_dir_from_workspace(self, fullpath, wspath):
        same, sysinfo, wsinfo = self._check_wspath_info(fullpath, wspath)
        if not same:
            self.set_path_info(fullpath, info=wsinfo)

    def _handle_inode_from_system(self, fullpath, wspath):
        if os.path.islink(fullpath):
            if os.path.islink(wspath):
                self._update_link_from_system(fullpath, wspath)
            else:
                self._import_link_from_system(fullpath, wspath)
        elif os.path.isdir(fullpath):
            if os.path.exists(wspath):
                self._update_empty_dir_from_system(fullpath, wspath)
            else:
                self._import_empty_dir_from_system(fullpath, wspath)
        elif os.path.isfile(fullpath):
            if os.path.exists(wspath):
                self._update_file_from_system(fullpath, wspath)
            else:
                self._import_file_from_system(fullpath, wspath)
        else:
            print 'ignoring', fullpath
            
    def _import_dir_from_system(self, fullpath):
        self._handle_intermediate_dirs(fullpath)
        for root, dirs, files in  os.walk(fullpath):
            wsroot = self._wspath(root)
            if not os.path.exists(wsroot):
                os.mkdir(wsroot)
                self.svn.add(wsroot)
                self._set_wspath_info(root, wsroot)
            for name in dirs:
                fname = join(root, name)
                wspath = self._wspath(fname)
                if os.path.islink(fname):
                    self._import_link_from_system(fname, wspath)
                else:
                    os.mkdir(wspath)
                    self.svn.add(wspath)
                    self._set_wspath_info(fname, wspath)
            for name in files:
                fname = join(root, name)
                wspath = self._wspath(fname)
                if os.path.islink(fname):
                    self._import_link_from_system(fname, wspath)
                else:
                    if os.path.isfile(fname):
                        self._import_file_from_system(fname, wspath)

    def _not_svndir(self, root):
        return os.path.basename(root) != '.svn' and root.find('/.svn/') == -1
    
    def _update_dir_from_system(self, fullpath):
        wspath = self._wspath(fullpath)
        for root, dirs, files in os.walk(fullpath):
            for name in dirs:
                fname = join(root, name)
                wsname = self._wspath(fname)
                self._handle_inode_from_system(fname, wsname)
            for name in files:
                fname = join(root, name)
                wsname = self._wspath(fname)
                self._handle_inode_from_system(fname, wsname)
        # remove from workspace
        for root, dirs, files in os.walk(wspath, topdown=False):
            if self._not_svndir(root):
                realroot = root.split(self.workspace)[1]
                #print 'realroot is', realroot
                for name in files:
                    fname = join(realroot, name)
                    if not os.path.exists(fname) and not os.path.islink(fname):
                        print 'removing', fname
                        self.svn.remove(self._wspath(fname))
                for name in dirs:
                    fname = join(realroot, name)
                    if name != '.svn' and fname.find('/.svn/') == -1:
                        if not os.path.exists(fname) and not os.path.islink(fname):
                            self.svn.remove(self._wspath(fname))

    def _export_dir_to_system(self, fullpath):
        wspath = self._wspath(fullpath)
        # remove dangling files first
        for root, dirs, files in os.walk(fullpath, topdown=False):
            for name in files:
                fname = join(root, name)
                wsname = self._wspath(fname)
                if not os.path.exists(wsname) and not os.path.islink(wsname):
                    print 'removing', fname
                    os.remove(fname)
            for name in dirs:
                fname = join(root, name)
                wsname = self._wspath(fname)
                if not os.path.exists(wsname):
                    print 'removing', fname
                    if os.islink(fname):
                        os.remove(fname)
                    else:
                        os.rmdir(fname)
        # export from workspace
        for root, dirs, files in os.walk(wspath):
            if self._not_svndir(root):
                realroot = root.split(self.workspace)[1]
                wsroot = self._wspath(realroot)
                #print 'realroot is', realroot
                if not os.path.exists(realroot):
                    os.mkdir(realroot)
                self._update_empty_dir_from_workspace(realroot, wsroot)
                for name in dirs:
                    if name != '.svn':
                        fname = join(realroot, name)
                        wspath = self._wspath(fname)
                        if os.path.islink(wspath):
                            if not os.path.exists(fname):
                                os.symlink(os.readlink(wspath), fname)
                            else:
                                self._update_link_from_workspace(fname, wspath)
                        else:
                            if not os.path.exists(fname):
                                os.mkdir(fname)
                            self._update_empty_dir_from_workspace(fname, wspath)
                for name in files:
                    fname = join(realroot, name)
                    wspath = self._wspath(fname)
                    if os.path.islink(wspath):
                        if not os.path.exists(fname) and not os.path.islink(fname):
                            os.symlink(os.readlink(wspath), fname)
                        else:
                            self._update_link_from_workspace(fname, wspath)
                    else:
                        if not os.path.exists(fname):
                            copyfile(wspath, fname)
                        self._update_file_from_workspace(fname, wspath)
        # fix mtimes on dirs
        for root, dirs, files in os.walk(self._wspath(fullpath), topdown=False):
            if self._not_svndir(root):
                realroot = root.split(self.workspace)[1]
                wsroot = self._wspath(realroot)
                for name in dirs:
                    fname = join(realroot, name)
                    wspath = self._wspath(fname)
                    if self._not_svndir(wspath):
                        if not os.path.islink(fname):
                            self._update_empty_dir_from_workspace(fname, wspath)
                self._update_empty_dir_from_workspace(realroot, wsroot)
                
    def set_path_info(self, fullpath, info):
        own = '%s:%s' % (info['user'], info['group'])
        os.system('chown %s "%s"' % (own, fullpath))
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
            make_new_config(cpath)
            self.svn.add(cpath)
        self.cfg.read(cpath)
        
    def commit(self, msg='Automatic Commit'):
        self.svn.checkin(self.workspace, msg)
        
    def show_status(self):
        os.system('svn status %s' % self.workspace)
        
    def get_filelist(self):
        return self.cfg.get_files('main')

    def check_file(self, fullpath, wspath=''):
        print 'this function is not ready'
        if not wspath:
            wspath = self._wspath(fullpath)
        return self._check_file_md5(fullpath, wspath)
    
    def check_files(self):
        print 'this function is not ready'
        sys.exit(1)
        
    def import_file(self, fullpath):
        files = self.cfg.get_files('main')
        dirs = [d for d in self.cfg.get_dirs('main') if fullpath.startswith(d)]
        if fullpath in files:
            print fullpath, 'already imported'
            sys.exit(1)
        if dirs:
            print fullpath, 'already imported'
            sys.exit(1)
        if os.path.islink(fullpath):
            print 'symlink arguments are not supported now'
            sys.exit(1)
            self._import_link_from_system(fullpath)
            self._append_to_cfg(fullpath, 'file')
        elif os.path.isfile(fullpath):
            print 'file arguments are not supported now'
            sys.exit(1)
            self._import_file_from_system(fullpath)
            self._append_to_cfg(fullpath, 'file')
        elif os.path.isdir(fullpath):
            self._import_dir_from_system(fullpath)
            self._append_to_cfg(fullpath, 'dir')
        else:
            print 'ignoring', fullpath

    def _append_to_cfg(self, fullpath, ftype):
        if ftype == 'file':
            members = self.cfg.get_files('main')
            option = 'files'
        elif ftype == 'dir':
            members = self.cfg.get_dirs('main')
            option = 'dirs'
        else:
            raise ValueError, 'bad ftype %s' % ftype
        members.append(fullpath)
        data = '\n'.join(members) + '\n'
        self.cfg.set('main', option, data)
        self.cfg.write(file(join(self.workspace, 'etcsvn.conf'), 'w'))
        
    def export_file(self, fullpath, section='main'):
        "old code"
        path = self._wspath(fullpath)
        symlink = False
        if not os.path.isfile(path):
            raise NoFileError, 'This file %s not in the repository' % fullpath
        if os.path.islink(path):
            symlink = True
            data = os.readlink(path)
        else:
            data = file(path).read()
        path = unroot(fullpath)
        dirs = os.path.dirname(path).split('/')
        rpath = '/'
        for d in dirs:
            rpath = join(rpath, d)
            if not os.path.isdir(rpath):
                os.mkdir(rpath)
            self.set_path_info(rpath, self.get_wspath_info(rpath))
        if symlink:
            os.symlink(fullpath, data)
        else:
            newfile = file(fullpath, 'w')
            newfile.write(data)
            newfile.close()
            info = self.get_wspath_info(fullpath)
            self.set_path_info(fullpath, info)

    def update_from_system(self):
        for adir in self.cfg.get_dirs('main'):
            self._update_dir_from_system(adir)
        for afile in self.cfg.get_files('main'):
            wspath = self._wspath(afile)
            if os.path.islink(afile):
                self._update_link_from_system(afile, wspath)
            else:
                self._update_file_from_system(afile, wspath)
    
    def export_to_system(self):
        for adir in self.cfg.get_dirs('main'):
            self._export_dir_to_system(adir)
        for afile in self.cfg.get_files('main'):
            print 'not exporting single files yet'
