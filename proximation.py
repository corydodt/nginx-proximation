#!/usr/bin/env python
"""
The proximation service
"""
import os
import signal
import shlex

from twisted.internet import reactor, utils
from twisted.python.procutils import which
from twisted.python import log

import attr

from jinja2 import Template

from codado.dockerish import DockerEngine


TEMPLATE = 'http.conf.in'
TEMPLATE_OUT = '/etc/nginx/conf.d/default.conf'
NGINX_PIDFILE = '/run/nginx/nginx.pid'
LETSENCRYPT_LIVE = '/etc/letsencrypt/live'
NGINX_WEBROOT = '/usr/share/nginx/html'


@attr.s
class VHost(object):
    """
    A record of a vhost being tracked by proximation
    """
    public_hostname = attr.ib()
    containers = attr.ib(default=attr.Factory(set))

    @property
    def hasPEM(self):
        return os.path.isdir('%s/%s' % (LETSENCRYPT_LIVE, self.public_hostname))


@attr.s
class EventWatcher(object):
    """
    Look for any started docker containers and build the nginx config based
    on their environment
    """
    engine = DockerEngine()
    _virtualHosts = attr.ib(default=attr.Factory(dict))

    def _scanContainers(self):
        """
        Rebuild internal container dict by looking at existing containers

        => True/False :: True if the container list has changed as a result of this event
        """
        running = self.engine.client.containers.list(filters={'status':'running'})

        vhosts = {}

        kv = lambda s: s.split('=', 1)
        for c in running:
            env = {k: v for (k, v) in (kv(s) for s in c.attrs['Config']['Env'])}
            if u'virtual_host' in env:
                public_hostname = env[u'virtual_host']
                vh = vhosts.get(public_hostname) or VHost(public_hostname=public_hostname)
                vh.containers.add(c)
                vhosts[public_hostname] = vh

        # have we changed?
        ret = vhosts != self._virtualHosts

        self._virtualHosts = vhosts
        return ret

    @engine.handler("dockerish.init")
    @engine.handler("container.stop")
    @engine.handler("container.pause")
    @engine.handler("container.start")
    @engine.handler("container.die")
    @engine.handler("container.kill")
    @engine.handler("container.unpause")
    def onStart(self, event):
        """
        Rebuild the nginx config
        """
        print event.name
        modified = self._scanContainers()
        if modified:
            self.render()
            print 'Rendered %r' % TEMPLATE_OUT
            # TODO: defer this a few seconds
            self.reload()
            for vh in self._virtualHosts.values():
                # FIXME - certbot will only run 1 at a time, so these have to
                # be chained together
                self.ensurePEM(vh)
            self.showHosts()

    def showHosts(self):
        print "Now:"
        for k, vh in self._virtualHosts.items():
            tls = '[TLS]' if vh.hasPEM else ''
            conts = [c.attrs['Config']['Hostname'] for c in vh.containers]
            print "  %s%s: %s" % (k, tls, ' '.join(conts))

    def reload(self):
        """
        Signal nginx to reload config
        """
        # TODO: test with nginx -T
        pid = int(open(NGINX_PIDFILE).read())
        os.kill(pid, signal.SIGHUP)

    def render(self):
        """
        Render the template
        """
        inputFile = open(TEMPLATE, 'rb')
        tpl = Template(inputFile.read())
        env = dict(__environ__=os.environ,
                virtual_hosts=self._virtualHosts.values(),
                **os.environ)
        open(TEMPLATE_OUT, 'wb').write(
            tpl.render(**env)
            )

    def ensurePEM(self, vhost):
        """
        Run certbot to get the PEM for this vhost, if necessary
        """
        if vhost.hasPEM:
            return

        pathCertbot = which('certbot')[0]
        args = shlex.split(
            '{flags} certonly -n '
            '--agree-tos -m {email} '
            '--webroot -w {webroot} '
            '--preferred-challenges http-01 '
            '-d {ph}'.format(
                webroot=NGINX_WEBROOT,
                ph=vhost.public_hostname,
                flags=os.environ.get('certbot_flags', ''),
                email=os.environ['certbot_email'],
                )
            )
        print "Attempting to get cert for %r" % vhost.public_hostname
        d = utils.getProcessOutputAndValue(pathCertbot, args)
        d.addCallback(self.onCertbot, vhost).addErrback(log.err)

    def onCertbot(self, (out, err, code), vhost):
        bad = "certbot failed:\n%r\n%r\n" % (out, err)
        assert code == 0 and 'Congratulations' in out,  bad

        self.render()
        self.reload()
        self.showHosts()

def main():
    ew = EventWatcher()
    # TODO: shut down early if the docker socket can't be found
    reactor.callWhenRunning(ew.engine.run)
    reactor.run()


main()
