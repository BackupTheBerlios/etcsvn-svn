import os
from os.path import join, isfile, isdir, islink, exists
from StringIO import StringIO
from md5 import md5
import pwd, grp
import subprocess

from defaults import BLOCK_SIZE

class strfile(StringIO):
    """I don't like the looks of StringIO and prefer
    a more pythonic type name.  Nothing special about
    this class.
    """
    def __init__(self, string=''):
        StringIO.__init__(self, string)

def makepaths(*paths):
    for path in paths:
        if not isdir(path):
            os.makedirs(path)

def md5sum(afile):
    """returns the standard md5sum hexdigest
    for a file object"""
    m = md5()
    block = afile.read(BLOCK_SIZE)
    while block:
        m.update(block)
        block = afile.read(BLOCK_SIZE)
    return m.hexdigest()

def ujoin(*args):
    """I think that this function name
    looks a little better and makes the code
    look a little better.
    """
    return '_'.join(args)

def unroot(fullpath):
    if fullpath[0] != '/':
        raise ValueError, 'absolute path to file needed.'
    path = fullpath
    while path[0] == '/':
        path = path[1:]
    return path

def get_file_info(fullpath):
    st = os.stat(fullpath)
    user = pwd.getpwuid(st.st_uid).pw_name
    group = grp.getgrgid(st.st_gid).gr_name
    mode = str(oct(st.st_mode))
    mtime = str(st.st_mtime)
    return dict(user=user, group=group, mode=mode, mtime=mtime)

def set_file_info(filename, info, verbose=False):
    owner = '%s:%s' % (info['user'], info['group'])
    if verbose:
        print "Owner is", owner
    subprocess.check_call(['chown', owner, filename])
    mode = info['mode']
    # I don't like using eval here, so we will
    # try to filter out bad values
    if len(mode) <= 7 and mode.isdigit():
        if verbose:
            print "Mode is", mode
        mode = eval(mode)
    else:
        raise RuntimeError , "Bad mode value, %s" % mode
    os.chmod(filename, mode)
    mtime = int(info['mtime'])
    if verbose:
        print "Mtime is", mtime
    os.utime(filename, (mtime, mtime))
    
def copyfile(src, dest):
    file(dest, 'w').writelines(file(src))

def remove_directory(directory):
    # copied from python library reference
    for root, dirs, files in os.walk(directory, topdown=False):
        for name in files:
            os.remove(join(root, name))
        for name in dirs:
            fname = join(root, name)
            if islink(fname):
                os.remove(fname)
            else:
                os.rmdir(join(root, name))
    os.rmdir(directory)
    

if __name__ == '__main__':
    print "don't run this file directly, unless testing it"
    
    
