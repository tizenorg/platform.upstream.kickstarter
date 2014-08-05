#!/usr/bin/python
import copy
import time
import yaml
import os, re
import sys
import errno
from urlparse import urlparse

from kickstart import kickstart

class KSMetaError(Exception):
    """Exception to catch malformated meta YAML files """
    def __init__(self, msg):
        Exception.__init__(self)
        self.msg = msg

    def __str__(self):
        return self.msg

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST:
            pass
        else: raise

def yamlload_safe(fname):
    """ Safer wrapper for yaml.load() """
    try:
        with file(fname) as f:
            return yaml.load(f)

    except IOError:
        raise KSMetaError('cannot read meta file: %s' % fname)

    except:
        # should be YAML format issue
        raise KSMetaError('format error of meta file: %s' % fname)

class KSWriter():
    def __init__(self, configs=None, repos=None, outdir=".", config=None, packages=False, external=None, targetdefs=None, target=None):
        self.dist = None
        self.arch = None
        self.image_filename = os.path.abspath(os.path.expanduser(configs))
        self.outdir = outdir
        self.external = external
        self.packages = packages
        self.config = config
        self.image_meta = yamlload_safe(self.image_filename)
        self.extra = {}

        self.repos = self.parse_repos(repos)

        # parse and record target definitions
        self.target = target
        self.targetdefs = self.parse_targetdef(targetdefs)

    def parse_repos(self, repos):
        prepos = []
        for repo in repos:
            repo_meta = yamlload_safe(repo)
            prepos = prepos + repo_meta['Repositories']

        return prepos

    def parse_targetdef(self, targetdefs):
        """ Parse the targets defs in YAML to list of dict.
            Will join them if multiple files provided.
            Once one wrong file found, raise exception to abort
        """
        if not targetdefs:
            return []

        all_defs = []
        for tdef in targetdefs:
            tmeta = yamlload_safe(tdef)

            all_defs.extend(tmeta['Targets'])

        return all_defs

    def merge(*input):
        return list(reduce(set.union, input, set()))

    def dump(self):
        print yaml.dump(yamlload_safe(self.stream))

    def parse(self, img):
        conf = copy.copy(self.image_meta['Default'])
        plat = copy.copy(self.image_meta[img['Platform']])
        conf.update(plat)
        conf.update(img)
        lval = ['Repos', 'Groups', 'PostScripts', 'NoChrootScripts', 'RemovePackages', 'ExtraPackages']
        lvald = {}
        for l in lval:
            full = []
            if self.image_meta['Default'].has_key(l) and self.image_meta['Default'][l]:
                full = full + self.image_meta['Default'][l]
            if plat.has_key(l) and plat[l]:
                full = full + plat[l]
            if img.has_key(l) and img[l]:
                full = full + img[l]
            lvald[l] = sorted(set(full), key=full.index)
        conf.update(lvald)
        postscript = ""
        meta_root = os.path.dirname(self.image_filename)
        for scr in conf['PostScripts']:
            if os.path.exists('%s/scripts/%s.post' %(meta_root, scr)):
                f = open('%s/scripts/%s.post' %(meta_root, scr), 'r')
                postscript += f.read()
                postscript += "\n"
                f.close()
            else:
                raise KSMetaError('%s/scripts/%s.post not found, aborting.' %(meta_root,scr ))

        nochrootscript = ""
        for scr in conf['NoChrootScripts']:
            if os.path.exists('%s/scripts/%s.nochroot' %(meta_root,scr)):
                f = open('%s/scripts/%s.nochroot' %(meta_root, scr ), 'r')
                nochrootscript += f.read()
                nochrootscript += "\n"
                f.close()
            else:
                raise KSMetaError('%s/scripts/%s.nochroot not found, aborting.' %(meta_root, scr ))

        ptab = ""
        for g in [ plat, img ]:
            if g.has_key("Part"):
                f = open("%s/partitions/%s" %(meta_root, g['Part']) )
                ptab = f.read()
                f.close()

        conf['Part'] = ptab
        conf['Post'] = postscript
        conf['NoChroot'] = nochrootscript
        return conf

    def process_files(self,  meta,  repos):
        new_repos = []
        if ( meta.has_key("Architecture") and  meta['Architecture'] )  or ( meta.has_key("Distribution") and  meta['Distribution']):
            for repo in repos:
                r = {}
                r['Name'] = repo['Name']
                repourl = repo['Url']
                if repo.has_key('Options'):
                    r['Options'] = repo['Options']
                if meta.has_key("Architecture") or self.arch:
                    repourl = repourl.replace("@ARCH@", self.arch or meta['Architecture'])
                if meta.has_key("Distribution") or self.dist:
                    repourl = repourl.replace("@DIST@", self.dist or meta['Distribution'])

                url = repourl.replace("@RELEASE@", meta['Baseline'])
                o = urlparse(url)
                new_url = "%s://" % o[0]
                if repo.has_key('Username') and repo['Username']:
                    new_url = "%s%s" % (new_url, repo['Username'] )
                if repo.has_key('Password') and repo['Password']:
                    new_url = "%s:%s@" % (new_url, repo['Password'] )
                r['Url'] = "%s%s%s" % (new_url, o[1], o[2] )
                new_repos.append(r)
        else:
            new_repos = repos

        nameSpace = {'metadata': meta,  'repos': new_repos}
        t = kickstart(searchList=[nameSpace])
        a = str(t)
        if meta.has_key('FileName') and meta['FileName']:
            f = None
            if meta.has_key("Baseline"):
                mkdir_p("%s/%s" %(self.outdir, meta['Baseline']))
                f = open("%s/%s/%s.ks" %( self.outdir, meta['Baseline'],  meta['FileName'] ), 'w')
            else:
                f = open("%s/%s.ks" %( self.outdir, meta['FileName'] ), 'w')
            f.write(a)
            f.close()

    def _image_for_current_target(self, fname):
        """ To check whether this image is belong to current
            target, which is specifed by user
        """

        if not self.target or not self.targetdefs:
            # if user doesn't specify them, skip the checking
            return True

        for tdef in self.targetdefs:
            if self.target == tdef['Name'] and fname in tdef['Images']:
                # found
                return True

        return False

    def generate(self):
        out = {}
        if self.image_meta.has_key('Configurations'):
            for img in self.image_meta['Configurations']:
                conf = self.parse(img)
                if self.config:
                    if img.has_key('FileName') and self.config == img['FileName']:
                        print "Creating %s (%s.ks)" %(img['Name'], img['FileName'] )
                        self.process_files(conf, self.repos)
                        break
                else:
                    if conf.has_key('Active') and conf['Active'] :
                        print "Creating %s (%s.ks)" %(img['Name'], img['FileName'] )
                        self.process_files(conf, self.repos)
                    else:
                        print "%s is inactive, not generating %s at this time" %(img['Name'], img['FileName'] )

        external = []
        if self.external:
            external = external + self.external
        if self.image_meta.has_key('ExternalConfigs') and self.image_meta['ExternalConfigs']:
            external = external + self.image_meta['ExternalConfigs']

        for path in external:
            external_config_dir = os.path.join(os.path.dirname(self.image_filename), path)
            if not os.path.exists(external_config_dir):
                external_config_dir = os.path.abspath(os.path.expanduser(path))

            for f in os.listdir(external_config_dir):
                if f.endswith('.yaml'):

                    if not self._image_for_current_target(f):
                        # skip
                        continue

                    local = yamlload_safe('%s/%s' %(external_config_dir, f))
                    conf = self.parse(local)
                    if self.config:
                        if self.config == conf['FileName']:
                            if self.packages:
                                out['baseline'] = conf['Baseline']
                                out['groups'] = conf['Groups']
                                out['packages'] = conf['ExtraPackages']
                            else:
                                print "Creating %s (%s.ks)" %(conf['Name'], conf['FileName'] )
                                self.process_files(conf, self.repos)
                                break
                    else:
                        if conf.has_key('Active') and conf['Active']:
                            print "Creating %s (%s.ks)" %(conf['Name'], conf['FileName'] )
                            self.process_files(conf, self.repos)
                        else:
                            print "%s is inactive, not generate %s this time" %(conf['Name'], conf['FileName'] )
                else:
                    print "WARNING: File '%s' ignored." % (f)
        return out
