#!/usr/bin/env python
"""
The proximation service
"""
import os
import signal
import shlex

from twisted.internet import reactor, utils, defer, task
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


def canonicalizeVirtualPort(n):
    """
    Returns a string in the format used by docker container NetworkSettings
    """
    n = str(n)
    return "%s/tcp" % n if "/" not in n else n


@attr.s
class VHost(object):
    """
    A record of a vhost being tracked by proximation
    """
    public_hostname = attr.ib()
    private_port = attr.ib(convert=canonicalizeVirtualPort, default='8080/tcp')
    containers = attr.ib(default=attr.Factory(set))

    @property
    def hasPEM(self):
        return os.path.isdir('%s/%s' % (LETSENCRYPT_LIVE, self.public_hostname))

    def mappedAddress(self, container):
        """
        Return the exposed IP and exposed port of the container
        """
        mapped_ip = container.attrs.NetworkSettings.IPAddress
        mapped_port = container.attrs.NetworkSettings.Ports[self.private_port][0]['HostPort']
        return (mapped_ip, mapped_port)


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
            if u'public_hostname' in env:
                public_hostname = env[u'public_hostname']
                private_port = env[u'private_port']
                vh = vhosts.get(public_hostname) or VHost(
                        public_hostname=public_hostname,
                        private_port=private_port
                        )
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
        modified = self._scanContainers()
        if modified:
            self.render()
            print 'Rendered %r' % TEMPLATE_OUT
            self._postRender()

    def _postRender(self):
        """
        Update nginx and certbot
        """
        self.reload()
        d = task.cooperate(self.ensurePEM(vh) for vh in
                self._virtualHosts.values()).whenDone()
        d.addCallback(lambda _: self.showHosts())

    def showHosts(self):
        """
        Display a formatted listing of all virtual hosts, with TLS status and
        associated containers
        """
        print "Now:"
        for k, vh in self._virtualHosts.items():
            tls = '[TLS]' if vh.hasPEM else ''
            hostports = []
            for c in vh.containers:
                ip, port = vh.mappedAddress(c)
                hostports.append(
                    '%s:%s' % (c.attrs['Config']['Hostname'], port)
                    )
            print u"  %s%s: %s" % (k, tls, u' '.join(hostports))

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
            return defer.succeed(None)

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
        return utils.getProcessOutputAndValue(pathCertbot, args
                ).addCallback(self.onCertbot, vhost
                ).addErrback(log.err)

    def onCertbot(self, (out, err, code), vhost):
        """
        When certbot setup has completed, refresh nginx
        """
        bad = "certbot failed:\n%r\n%r\n" % (out, err)
        assert code == 0 and 'Congratulations' in out,  bad

        self.render()
        self._postRender()


def main():
    ew = EventWatcher()
    # TODO: shut down early if the docker socket can't be found
    reactor.callWhenRunning(ew.engine.run)
    reactor.run()


main()
