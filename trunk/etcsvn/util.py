#import os, sys
#from os.path import isfile, isdir, join
#from gzip import GzipFile
import os
from StringIO import StringIO
from md5 import md5
import pwd, grp

from defaults import BLOCK_SIZE
#from pipes import Template as PipeTemplate
#import pycurl

#from useless.base import debug, Error

#from defaults import BLOCK_SIZE

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
    mode = oct(st.st_mode)
    mtime = st.st_mtime
    return dict(user=user, group=group, mode=mode, mtime=mtime)



if __name__ == '__main__':
    print "don't run this file directly, unless testing it"
    
    
